from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path

from claudechat.config import Config

_log = logging.getLogger("claudechat.engine")

_MAX_BODY_BYTES = 64 * 1024
_ALLOWED_FIELDS = {"text", "cwd"}


def peer_uid_via_libc(connection: socket.socket) -> int | None:
    """getpeereid(fd, &uid, &gid) — the macOS/BSD equivalent of SO_PEERCRED.

    Returns None when the peer cannot be identified, which callers must treat
    as "reject". glibc does not export this symbol at all, so the lookup raises
    AttributeError there rather than failing at runtime — Linux uses
    SO_PEERCRED and never reaches this function.
    """
    import ctypes
    import ctypes.util

    library = ctypes.util.find_library("c")
    if library is None:
        return None
    try:
        libc = ctypes.CDLL(library, use_errno=True)
        getpeereid = libc.getpeereid
    except (OSError, AttributeError):
        return None

    uid = ctypes.c_uint32()
    gid = ctypes.c_uint32()
    try:
        if getpeereid(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            return None
    except (OSError, ValueError):
        return None
    return uid.value


class RateLimiter:
    """A loop breaker, not a conversation throttle.

    This exists to stop a misfiring hook triggering summarise calls in a tight
    loop and draining Claude quota. It is deliberately short: a person replying
    a second after the last reply is having a conversation, not flooding you,
    and dropping that reply makes the tool feel broken. The real protection
    against runaway cost is the recursion guard on internal calls.
    """

    def __init__(self, min_interval_seconds: float) -> None:
        self._interval, self._last = min_interval_seconds, None

    def allow(self, now: float) -> bool:
        if self._last is not None and now - self._last < self._interval:
            return False
        self._last = now
        return True


class EngineService:
    """Unix socket exposing only the announcement operation."""

    def __init__(self, config: Config, on_announce: Callable[[str, str], None], on_drop: Callable[[], None] | None = None) -> None:
        self._config, self._on_announce, self._on_drop = config, on_announce, on_drop
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
        cwd = payload.get("cwd", "")
        if not isinstance(cwd, str):
            self._reply(connection, b'{"status":"error","reason":"bad cwd"}')
            return
        if not self._limiter.allow(time.monotonic()):
            if self._on_drop is not None:
                try:
                    self._on_drop()
                except Exception:
                    pass
            _log.info("DROPPED (rate limited, one per %.0fs): %.60s",
                      self._config.hook_min_interval_seconds, text.replace("\n", " "))
            self._reply(connection, b'{"status":"dropped","reason":"rate limited"}')
            return
        _log.info("ACCEPTED %d chars: %.60s", len(text), text.replace("\n", " "))
        self._on_announce(text, cwd)
        self._reply(connection, b'{"status":"ok"}')

    @staticmethod
    def _peer_is_owner(connection: socket.socket) -> bool:
        """Reject any connection not owned by this user.

        Linux exposes SO_PEERCRED as a socket option. macOS does not — it has
        getpeereid(3) in libc instead. Without the second branch this returned
        False for every connection on macOS: it failed closed, which is the
        right direction, but it made the daemon unusable there.
        """
        try:
            if hasattr(socket, "SO_PEERCRED"):
                raw = connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                )
                _, uid, _ = struct.unpack("3i", raw)
                return uid == os.getuid()
            return peer_uid_via_libc(connection) == os.getuid()
        except OSError:
            return False
