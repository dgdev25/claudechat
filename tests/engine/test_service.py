import json
import socket
import stat
from dataclasses import replace

from claudechat.config import Config
from claudechat.engine.service import EngineService, RateLimiter


def _send(path, payload: bytes) -> bytes:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(path))
    client.sendall(payload)
    client.shutdown(socket.SHUT_WR)
    data = client.recv(4096)
    client.close()
    return data


def test_rate_limiter_allows_then_blocks():
    limiter = RateLimiter(min_interval_seconds=10.0)
    assert limiter.allow(now=100.0)
    assert not limiter.allow(now=105.0)
    assert limiter.allow(now=111.0)


def test_socket_is_owner_only(tmp_path):
    config = replace(Config(), runtime_dir=tmp_path / "run")
    service = EngineService(config, on_announce=lambda text: None)
    path = service.start()
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        service.stop()


def test_accepts_a_valid_announcement(tmp_path):
    seen = []
    config = replace(Config(), runtime_dir=tmp_path / "run")
    service = EngineService(config, on_announce=seen.append)
    path = service.start()
    try:
        assert b"ok" in _send(path, json.dumps({"text": "All tests passed."}).encode())
        assert seen == ["All tests passed."]
    finally:
        service.stop()


def test_rejects_oversized_body(tmp_path):
    seen = []
    service = EngineService(replace(Config(), runtime_dir=tmp_path / "run"), seen.append)
    path = service.start()
    try:
        assert b"error" in _send(path, b'{"text":"' + b"x" * (200 * 1024) + b'"}')
        assert seen == []
    finally:
        service.stop()


def test_rejects_unknown_fields(tmp_path):
    seen = []
    service = EngineService(replace(Config(), runtime_dir=tmp_path / "run"), seen.append)
    path = service.start()
    try:
        assert b"error" in _send(path, json.dumps({"text": "hi", "model": "evil"}).encode())
        assert seen == []
    finally:
        service.stop()


def _send_without_reading(path, text: str) -> None:
    """Reproduce exactly what the hook script does: send, shutdown, close.

    It never reads the reply, so the server's sendall raises BrokenPipeError.
    That previously escaped the serve loop and killed the thread, so only the
    first announcement of a session ever worked.
    """
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(str(path))
    client.sendall(json.dumps({"text": text}).encode())
    client.shutdown(socket.SHUT_WR)
    client.close()


def test_survives_clients_that_close_without_reading(tmp_path):
    import time

    seen = []
    config = replace(
        Config(), runtime_dir=tmp_path / "run", hook_min_interval_seconds=0.0
    )
    service = EngineService(config, on_announce=seen.append)
    path = service.start()
    try:
        _send_without_reading(path, "first")
        time.sleep(0.4)
        _send_without_reading(path, "second")
        time.sleep(0.4)
        assert seen == ["first", "second"], f"server stopped accepting: {seen}"
    finally:
        service.stop()
