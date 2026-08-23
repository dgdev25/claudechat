from __future__ import annotations

import json
import os
import socket
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path

from claudechat.config import Config

_MAX_BODY_BYTES = 64 * 1024
_ALLOWED_FIELDS = {"text"}


class RateLimiter:
    """Drop-on-overload: announcements are never queued."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._interval, self._last = min_interval_seconds, None

    def allow(self, now: float) -> bool:
        if self._last is not None and now - self._last < self._interval:
            return False
        self._last = now
        return True


class EngineService:
    """Unix socket exposing only the announcement operation."""

    def __init__(self, config: Config, on_announce: Callable[[str], None]) -> None:
        self._config, self._on_announce = config, on_announce
        self._limiter = RateLimiter(config.hook_min_interval_seconds)
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.socket_path = config.runtime_dir / "engine.sock"

    def start(self) -> Path:
        directory = self.socket_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        if self.socket_path.exists():
            if not self.socket_path.is_socket() or self.socket_path.stat().st_uid != os.getuid():
                raise RuntimeError(f"refusing to replace {self.socket_path}")
            self.socket_path.unlink()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.socket_path))
        self.socket_path.chmod(0o600)
        self._server.listen(4)
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self.socket_path

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.socket_path.unlink(missing_ok=True)

    def _serve(self) -> None:
        while self._running and self._server is not None:
            try:
                connection, _ = self._server.accept()
            except OSError:
                return
            try:
                self._handle(connection)
            except Exception:
                # One misbehaving client must never take the server down. The
                # hook script sends and closes without reading the reply, so
                # sendall raises BrokenPipeError — which previously killed this
                # thread, silently disabling every announcement after the first.
                pass
            finally:
                try:
                    connection.close()
                except OSError:
                    pass

    @staticmethod
    def _reply(connection: socket.socket, body: bytes) -> None:
        """Best-effort reply: the client may already have closed."""
        try:
            connection.sendall(body)
        except OSError:
            pass

    def _handle(self, connection: socket.socket) -> None:
        if not self._peer_is_owner(connection):
            self._reply(connection, b'{"status":"error","reason":"peer rejected"}')
            return
        body = b""
        while len(body) <= _MAX_BODY_BYTES:
            block = connection.recv(4096)
            if not block:
                break
            body += block
        if len(body) > _MAX_BODY_BYTES:
            self._reply(connection, b'{"status":"error","reason":"too large"}')
            return
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._reply(connection, b'{"status":"error","reason":"malformed"}')
            return
        if not isinstance(payload, dict) or set(payload) - _ALLOWED_FIELDS:
            self._reply(connection, b'{"status":"error","reason":"unexpected fields"}')
            return
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            self._reply(connection, b'{"status":"error","reason":"no text"}')
            return
        if not self._limiter.allow(time.monotonic()):
            self._reply(connection, b'{"status":"dropped","reason":"rate limited"}')
            return
        self._on_announce(text)
        self._reply(connection, b'{"status":"ok"}')

    @staticmethod
    def _peer_is_owner(connection: socket.socket) -> bool:
        try:
            raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _, uid, _ = struct.unpack("3i", raw)
            return uid == os.getuid()
        except OSError:
            return False
