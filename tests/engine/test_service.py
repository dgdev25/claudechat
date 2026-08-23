import json
import os
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
    service = EngineService(config, on_announce=lambda text, cwd: seen.append((text, cwd)))
    path = service.start()
    try:
        assert b"ok" in _send(path, json.dumps({"text": "All tests passed."}).encode())
        assert seen == [("All tests passed.", "")]
    finally:
        service.stop()


def test_rejects_oversized_body(tmp_path):
    seen = []
    service = EngineService(replace(Config(), runtime_dir=tmp_path / "run"), lambda text, cwd: seen.append((text, cwd)))
    path = service.start()
    try:
        assert b"error" in _send(path, b'{"text":"' + b"x" * (200 * 1024) + b'"}')
        assert seen == []
    finally:
        service.stop()


def test_rejects_unknown_fields(tmp_path):
    seen = []
    service = EngineService(replace(Config(), runtime_dir=tmp_path / "run"), lambda text, cwd: seen.append((text, cwd)))
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
    service = EngineService(config, on_announce=lambda text, cwd: seen.append(text))
    path = service.start()
    try:
        _send_without_reading(path, "first")
        time.sleep(0.4)
        _send_without_reading(path, "second")
        time.sleep(0.4)
        assert seen == ["first", "second"], f"server stopped accepting: {seen}"
    finally:
        service.stop()


def test_peer_check_uses_so_peercred_on_linux(tmp_path):
    """The Linux path must keep working — it is the one in production use."""
    import socket as socketlib

    assert hasattr(socketlib, "SO_PEERCRED"), "this test only means anything on Linux"

    seen = []
    config = replace(Config(), runtime_dir=tmp_path / "run", hook_min_interval_seconds=0.0)
    service = EngineService(config, on_announce=lambda text, cwd: seen.append(text))
    path = service.start()
    try:
        reply = _send(path, json.dumps({"text": "accepted"}).encode())
        assert b"ok" in reply, "own-UID connection must be accepted"
    finally:
        service.stop()


def test_libc_peer_lookup_degrades_to_none_not_a_crash():
    """glibc has no getpeereid; the helper must return None, never raise.

    Returning None means 'cannot identify the peer', which _peer_is_owner
    treats as reject. macOS has the symbol and returns a real uid.
    """
    import socket as socketlib

    from claudechat.engine.service import peer_uid_via_libc

    left, right = socketlib.socketpair(socketlib.AF_UNIX, socketlib.SOCK_STREAM)
    try:
        result = peer_uid_via_libc(left)
        assert result is None or result == os.getuid()
    finally:
        left.close()
        right.close()


def test_on_drop_callback_invoked_on_rate_limited_request(tmp_path):
    """Verify that on_drop is called exactly once for the second rapid request."""
    import time

    drop_count = [0]

    def on_drop():
        drop_count[0] += 1

    config = replace(Config(), runtime_dir=tmp_path / "run", hook_min_interval_seconds=1.0)
    service = EngineService(config, on_announce=lambda text, cwd: None, on_drop=on_drop)
    path = service.start()
    try:
        # Send two announcements rapidly.
        _send(path, json.dumps({"text": "first"}).encode())
        _send(path, json.dumps({"text": "second"}).encode())
        time.sleep(0.1)  # Let async processing finish.
        assert drop_count[0] == 1, f"on_drop should be called once, got {drop_count[0]}"
    finally:
        service.stop()


def test_on_drop_exception_does_not_prevent_reply(tmp_path):
    """Verify that even if on_drop raises, the client still receives a response."""
    import time

    def on_drop_raises():
        raise ValueError("intentional error in on_drop")

    config = replace(Config(), runtime_dir=tmp_path / "run", hook_min_interval_seconds=1.0)
    seen = []
    service = EngineService(config, on_announce=lambda text, cwd: seen.append(text), on_drop=on_drop_raises)
    path = service.start()
    try:
        # Send first request.
        reply1 = _send(path, json.dumps({"text": "first"}).encode())
        assert b"ok" in reply1
        # Send second request immediately (will be rate-limited).
        reply2 = _send(path, json.dumps({"text": "second"}).encode())
        assert b"dropped" in reply2 or b"error" in reply2, "client should get a response even if on_drop raised"
        time.sleep(0.1)
        assert seen == ["first"], "first announcement should be seen, second dropped"
    finally:
        service.stop()


def test_message_with_text_and_cwd_reaches_on_announce_with_both_values(tmp_path):
    """GATE 2b: message with text and cwd are both passed to on_announce."""
    seen = []
    config = replace(Config(), runtime_dir=tmp_path / "run")
    service = EngineService(config, on_announce=lambda text, cwd: seen.append((text, cwd)))
    path = service.start()
    try:
        reply = _send(path, json.dumps({"text": "test message", "cwd": "/home/user/project"}).encode())
        assert b"ok" in reply
        assert seen == [("test message", "/home/user/project")]
    finally:
        service.stop()


def test_bad_cwd_type_is_rejected(tmp_path):
    """GATE 2b: if cwd is not a string, the request is rejected."""
    seen = []
    service = EngineService(replace(Config(), runtime_dir=tmp_path / "run"), lambda text, cwd: seen.append((text, cwd)))
    path = service.start()
    try:
        reply = _send(path, json.dumps({"text": "hi", "cwd": 123}).encode())
        assert b"error" in reply
        assert b"bad cwd" in reply
        assert seen == []
    finally:
        service.stop()
