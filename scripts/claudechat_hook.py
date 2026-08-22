#!/usr/bin/env python3
"""Claude Code Stop hook: hand the reply to the claudechat engine.

Exits 0 in every path. Claude Code must never wait on or fail because of speech.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


_TIMEOUT_SECONDS = 1.0
_MAX_TEXT_CHARS = 32000


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / "claudechat"
    return Path.home() / ".cache" / "claudechat" / "run"


def main() -> int:
    runtime = _runtime_dir()

    # Recursion control (ADR 0006): our own CLI calls trigger the Stop hook.
    marker = os.environ.get("CLAUDECHAT_INTERNAL")
    if marker:
        try:
            if (runtime / "token").read_text().strip() == marker.strip():
                print("suppressed: internal call", file=sys.stderr)
                return 0
        except OSError:
            pass

    try:
        payload = json.load(sys.stdin)
        text = str(payload.get("last_assistant_message") or "")[:_MAX_TEXT_CHARS]
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    if not text.strip():
        return 0

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(_TIMEOUT_SECONDS)
            client.connect(str(runtime / "engine.sock"))
            client.sendall(json.dumps({"text": text}).encode())
            client.shutdown(socket.SHUT_WR)
    except (OSError, socket.timeout):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
