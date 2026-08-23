"""One long-lived Claude process, reused across turns.

Starting `claude -p` costs a measured 0.89 s before a single token appears, and
process-per-turn pays that on every turn. This keeps one process alive and feeds
it messages, so only the first turn pays.

Cancellation drops the process rather than reusing it. Draining an abandoned
turn so the process could be kept was measured at 29 s before the next turn
could start — the abandoned reply had to finish generating first, which is far
worse than the 0.9 s persistence saves. So barge-in costs one cold start, and
only uncancelled turns chain.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Iterator

from claudechat.claude.runner import Event, parse_stream_line
from claudechat.config import Config

_MAX_LINE_BYTES = 1 << 20


class PersistentClaudeRunner:
    """Drop-in replacement for ClaudeRunner that reuses one CLI process.

    One turn at a time, enforced by a lock — the CLI has a single stdout stream,
    so two concurrent turns would read each other's tokens.
    """

    def __init__(self, config: Config, internal_token: str, system_prompt: str) -> None:
        self._config = config
        self._token = internal_token
        self._system_prompt = system_prompt
        self._process: subprocess.Popen | None = None
        self._turn_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._binary = shutil.which("claude")
        if self._binary is None:
            raise RuntimeError("claude CLI not found on PATH")

    # ---- process lifecycle -------------------------------------------------

    def _argv(self) -> list[str]:
        return [
            self._binary, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--model", "sonnet",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--tools", "",
            "--disable-slash-commands",
            "--exclude-dynamic-system-prompt-sections",
            "--system-prompt", self._system_prompt,
            "--settings", '{"enabledPlugins":{}}',
        ]

    def _environment(self) -> dict[str, str]:
        keep = ("HOME", "PATH", "USER", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "TERM")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env["CLAUDECHAT_INTERNAL"] = self._token
        return env

    def _alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _ensure_process(self) -> subprocess.Popen:
        if self._alive():
            return self._process  # type: ignore[return-value]
        self._terminate()
        self._process = subprocess.Popen(
            self._argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=self._environment(),
            text=True,
            bufsize=1,
            start_new_session=True,
            shell=False,
        )
        return self._process

    def _terminate(self) -> None:
        """Kill the process group. The CLI spawns children that survive a bare kill."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=2.0)
        except (ProcessLookupError, PermissionError):
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait(timeout=1.0)
            except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
                pass

    # ---- turns -------------------------------------------------------------

    def stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        session_id: str | None = None,
    ) -> Iterator[Event]:
        """Yield one turn's events. session_id is accepted and ignored: the
        process holds the conversation itself, so there is nothing to resume."""
        with self._turn_lock:
            self._cancelled.clear()
            process = self._ensure_process()
            message = {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
            }
            try:
                process.stdin.write(json.dumps(message) + "\n")  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, ValueError, OSError):
                # The process died between the liveness check and the write.
                self._terminate()
                process = self._ensure_process()
                process.stdin.write(json.dumps(message) + "\n")  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]

            completed = False
            try:
                for line in process.stdout:  # type: ignore[union-attr]
                    if self._cancelled.is_set():
                        break
                    if len(line) > _MAX_LINE_BYTES:
                        break
                    event = parse_stream_line(line)
                    if event is None:
                        continue
                    yield event
                    if event.kind == "result":
                        completed = True
                        break
            finally:
                if not completed:
                    # Any turn that did not reach its result leaves the stream at
                    # an unknown position, so the process is dropped — not only on
                    # an explicit cancel. A caller that stops iterating early
                    # (took the first sentence and moved on) is just as dangerous:
                    # measured, the next turn read the tail of the abandoned reply
                    # and spoke "ue light reaches your eyes" as its answer.
                    #
                    # Draining instead, to keep the process, was measured at 29s
                    # before the next turn could start. A cold start is cheaper.
                    self._terminate()

    def cancel(self) -> None:
        """Abandon the current turn. The process is dropped; see module docstring."""
        self._cancelled.set()

    def close(self) -> None:
        """Shut the process down for good."""
        self._cancelled.set()
        self._terminate()
