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

    def __init__(self, config: Config, internal_token: str) -> None:
        self._config = config
        self._token = internal_token
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._binary = shutil.which("claude")
        if self._binary is None:
            raise RuntimeError("claude CLI not found on PATH")

    def _argv(self, system_prompt: str, session_id: str | None) -> list[str]:
        argv = [self._binary, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--model", "sonnet", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "", "--disable-slash-commands", "--exclude-dynamic-system-prompt-sections", "--system-prompt", system_prompt, "--settings", '{"enabledPlugins":{}}']
        if session_id:
            argv += ["--resume", session_id]
        return argv

    def _environment(self) -> dict[str, str]:
        keep = ("HOME", "PATH", "USER", "LANG", "LC_ALL", "XDG_RUNTIME_DIR", "TERM")
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env["CLAUDECHAT_INTERNAL"] = self._token
        return env

    def stream(self, prompt: str, system_prompt: str = VOICE_SYSTEM_PROMPT, session_id: str | None = None) -> Iterator[Event]:
        with self._lock:
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

    def cancel(self) -> None:
        with self._lock:
            self._terminate_locked()

    def _terminate_locked(self) -> None:
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
