import json
import socket
import subprocess
import sys
from pathlib import Path


HOOK = Path("scripts/claudechat_hook.py")


def _run(payload: dict, env: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    full_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", **env}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=10,
    )


def test_exits_zero_when_the_engine_is_absent(tmp_path):
    result = _run({"last_assistant_message": "hello"}, {"XDG_RUNTIME_DIR": str(tmp_path)}, tmp_path)
    assert result.returncode == 0


def test_exits_zero_on_a_malformed_payload(tmp_path):
    full_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        env=full_env,
        timeout=10,
    )
    assert result.returncode == 0


def test_internal_marker_suppresses_the_hook(tmp_path):
    runtime = tmp_path / "claudechat"
    runtime.mkdir(parents=True)
    (runtime / "token").write_text("secret-token")
    result = _run(
        {"last_assistant_message": "hello"},
        {"XDG_RUNTIME_DIR": str(tmp_path), "CLAUDECHAT_INTERNAL": "secret-token"},
        tmp_path,
    )
    assert result.returncode == 0
    assert "suppressed" in result.stderr.lower() or result.stdout == ""


def test_claudechat_mute_suppresses_the_hook(tmp_path):
    """GATE 1: when CLAUDECHAT_MUTE is set, the hook exits without sending."""
    result = _run(
        {"last_assistant_message": "hello"},
        {"CLAUDECHAT_MUTE": "1"},
        tmp_path,
    )
    assert result.returncode == 0


def test_internal_marker_never_connects_to_the_engine(tmp_path):
    runtime = tmp_path / "claudechat"
    runtime.mkdir(parents=True)
    (runtime / "token").write_text("secret-token")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(runtime / "engine.sock"))
    server.listen(1)
    server.settimeout(0.2)
    try:
        result = _run(
            {"last_assistant_message": "hello"},
            {"XDG_RUNTIME_DIR": str(tmp_path), "CLAUDECHAT_INTERNAL": "secret-token"},
            tmp_path,
        )
        assert result.returncode == 0
        try:
            server.accept()
        except TimeoutError:
            pass
        else:
            raise AssertionError("internal hook call connected to the engine")
    finally:
        server.close()


def test_installer_adds_the_stop_hook(tmp_path):
    sys.path.insert(0, "scripts")
    from install_hook import install_hook

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "opus"}))
    install_hook(settings, Path("/opt/claudechat/hook.py"))

    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    commands = [
        entry["command"]
        for group in data["hooks"]["Stop"]
        for entry in group["hooks"]
    ]
    assert any("hook.py" in command for command in commands)


def test_installer_is_idempotent(tmp_path):
    sys.path.insert(0, "scripts")
    from install_hook import install_hook

    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    install_hook(settings, Path("/opt/claudechat/hook.py"))
    install_hook(settings, Path("/opt/claudechat/hook.py"))

    data = json.loads(settings.read_text())
    groups = data["hooks"]["Stop"]
    commands = [entry["command"] for group in groups for entry in group["hooks"]]
    assert len([command for command in commands if "hook.py" in command]) == 1


def test_payload_cwd_is_forwarded_in_the_message(tmp_path):
    """GATE 2a: cwd from the payload is forwarded in the socket message."""
    runtime = tmp_path / "claudechat"
    runtime.mkdir(parents=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(runtime / "engine.sock"))
    server.listen(1)
    server.settimeout(1.0)
    try:
        full_env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": str(tmp_path)}
        import threading
        received_msg = []
        def accept_once():
            connection, _ = server.accept()
            data = connection.recv(4096)
            received_msg.append(json.loads(data.decode()))
            connection.close()
        thread = threading.Thread(target=accept_once)
        thread.start()
        subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"last_assistant_message": "hello", "cwd": "/home/user/project"}),
            capture_output=True,
            text=True,
            env=full_env,
            timeout=5,
        )
        thread.join(timeout=2.0)
        assert len(received_msg) == 1
        assert received_msg[0]["text"] == "hello"
        assert received_msg[0]["cwd"] == "/home/user/project"
    finally:
        server.close()
