import json
import socket
import stat
import time
from dataclasses import replace

import pytest

from claudechat.cli.terminal import Engine
from claudechat.config import Config


@pytest.mark.slow
def test_announcement_reaches_speech(tmp_path):
    config = replace(
        Config(),
        runtime_dir=tmp_path / "run",
        spoken_summaries=True,
        summary_threshold_chars=10000,
        hook_min_interval_seconds=0.0,
    )
    engine = Engine(config)
    spoken = []
    engine.speak = spoken.append
    engine.start()
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(engine.service.socket_path))
        client.sendall(json.dumps({"text": "The build finished.", "cwd": ""}).encode())
        client.shutdown(socket.SHUT_WR)
        client.recv(1024)
        client.close()
        time.sleep(0.5)
        assert spoken == ["The build finished."]
    finally:
        engine.stop()


@pytest.mark.slow
def test_token_file_is_written_owner_only(tmp_path):
    config = replace(Config(), runtime_dir=tmp_path / "run")
    engine = Engine(config)
    engine.start()
    try:
        token_file = config.runtime_dir / "token"
        assert token_file.read_text().strip()
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    finally:
        engine.stop()


@pytest.mark.slow
def test_stop_removes_socket_and_token(tmp_path):
    config = replace(Config(), runtime_dir=tmp_path / "run")
    engine = Engine(config)
    engine.start()
    socket_path = engine.service.socket_path
    engine.stop()
    assert not socket_path.exists()
    assert not (config.runtime_dir / "token").exists()
