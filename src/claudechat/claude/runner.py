from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from claudechat.config import Config

VOICE_SYSTEM_PROMPT = (
    "You are a voice assistant being read aloud through speakers. "
    "Reply in at most three short spoken sentences. "
    "Never use markdown, lists, headings, or code blocks. "
    "Write numbers and symbols as words a person would say."
)
_MAX_LINE_BYTES = 1 << 20
_MAX_TOTAL_BYTES = 8 << 20


@dataclass(frozen=True)
class Event:
    kind: Literal["text", "result"]
    text: str
    session_id: str | None


def parse_stream_line(line: str) -> Event | None:
    """Turn one stream-json line into an Event, or None if it carries nothing."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if payload.get("type") == "stream_event":
        delta = payload.get("event", {}).get("delta", {})
        if delta.get("type") == "text_delta":
            return Event("text", delta.get("text", ""), None)
    elif payload.get("type") == "result":
        return Event("result", payload.get("result", "") or "", payload.get("session_id"))
    return None


class ClaudeRunner:
    """Run one Claude turn through the CLI, streaming text out."""

    def __init__(self, config: Config, internal_token: str, model: str | None = None) -> None:
        self._config = config
        self._token = internal_token
        self._model = model
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._binary = shutil.which("claude")
        if self._binary is None:
            raise RuntimeError("claude CLI not found on PATH")
        self._stashed_process: subprocess.Popen[str] | None = None
        self._stashed_system_prompt: str | None = None
        self._closed = False
        self._closed_event = threading.Event()

    def _argv(self, system_prompt: str, session_id: str | None) -> list[str]:
        model = self._model or self._config.claude_model
        argv = [self._binary, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--model", model, "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "", "--disable-slash-commands", "--exclude-dynamic-system-prompt-sections", "--system-prompt", system_prompt, "--settings", '{"enabledPlugins":{}}']
        if session_id:
            argv += ["--resume", session_id]
        return argv

    def _environment(self) -> dict[str, str]:
        keep = ("HOME", "PATH", "USER", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "TERM")
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env["CLAUDECHAT_INTERNAL"] = self._token
        return env

    def prewarm(self, system_prompt: str = VOICE_SYSTEM_PROMPT) -> None:
        """Spawn a process in the background for the next stream() call."""
        # Fast path: check if close was called (thread-safe via Event)
        if self._closed_event.is_set():
            return
        with self._lock:
            # Double-check _closed after acquiring lock
            if self._closed:
                return
            if self._stashed_process is not None:
                # Already have a stashed process
                return
            try:
                self._stashed_process = subprocess.Popen(
                    self._argv(system_prompt, None),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env=self._environment(),
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                    shell=False,
                )
                self._stashed_system_prompt = system_prompt
            except Exception:
                # Never raise on spawn failure (drop the stash)
                self._stashed_process = None
                self._stashed_system_prompt = None

    def stream(self, prompt: str, system_prompt: str = VOICE_SYSTEM_PROMPT, session_id: str | None = None) -> Iterator[Event]:
        with self._lock:
            # Check if we can reuse the stashed process
            reuse_stash = (
                self._stashed_process is not None
                and self._stashed_system_prompt == system_prompt
                and session_id is None
                and self._stashed_process.poll() is None
            )

            if reuse_stash:
                # Reuse the stashed process
                self._terminate_locked()
                self._process = self._stashed_process
                self._stashed_process = None
                self._stashed_system_prompt = None
            else:
                # Discard the stash (if any) and spawn a new process
                self._kill_process(self._stashed_process)
                self._stashed_process = None
                self._stashed_system_prompt = None

                self._terminate_locked()
                self._process = subprocess.Popen(self._argv(system_prompt, session_id), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=self._environment(), text=True, bufsize=1, start_new_session=True, shell=False)

            process = self._process
        try:
            if process.stdin:
                process.stdin.write(prompt)
                process.stdin.close()
            total = 0
            for line in process.stdout or ():
                total += len(line)
                if len(line) > _MAX_LINE_BYTES or total > _MAX_TOTAL_BYTES:
                    break
                event = parse_stream_line(line)
                if event is not None:
                    yield event
        finally:
            self.cancel()
            # Schedule prewarm on a daemon thread if not closed
            if not self._closed:
                def delayed_prewarm() -> None:
                    # Brief delay allows close() to set _closed_event if called
                    import time
                    time.sleep(0.001)
                    self.prewarm(system_prompt)

                thread = threading.Thread(target=delayed_prewarm, daemon=True)
                thread.start()

    def cancel(self) -> None:
        with self._lock:
            self._terminate_locked()

    def close(self) -> None:
        """Close the runner and prevent further prewarming."""
        # Set the event first to prevent daemon thread from spawning
        self._closed_event.set()
        with self._lock:
            self._closed = True
            self._terminate_locked()
            self._kill_process(self._stashed_process)
            self._stashed_process = None
            self._stashed_system_prompt = None

    def _kill_process(self, process: subprocess.Popen[str] | None) -> None:
        """Kill a process with SIGTERM then SIGKILL if needed."""
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

    def _terminate_locked(self) -> None:
        process, self._process = self._process, None
        self._kill_process(process)
