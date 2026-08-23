"""Tests for PipeWire echo cancellation setup."""

import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudechat.cli.echocancel import PIPEWIRE_CONF, command_setup, conf_path


def test_conf_path_returns_correct_location(monkeypatch):
    """Test that conf_path returns the expected PipeWire config path."""
    monkeypatch.setenv("HOME", "/test/home")
    path = conf_path()
    assert str(path) == "/test/home/.config/pipewire/pipewire.conf.d/99-claudechat-echo-cancel.conf"


def test_pipewire_conf_has_exact_node_names():
    """Test that PIPEWIRE_CONF contains the exact node names expected."""
    assert "claudechat_ec_source" in PIPEWIRE_CONF
    assert "claudechat_ec_sink" in PIPEWIRE_CONF
    assert "claudechat_ec_capture" in PIPEWIRE_CONF
    assert "claudechat_ec_playback" in PIPEWIRE_CONF
    assert "libpipewire-module-echo-cancel" in PIPEWIRE_CONF


def test_setup_returns_1_on_macos(monkeypatch, tmp_path):
    """Test that setup returns 1 on macOS without writing files."""
    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: True)
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", tmp_path / "config.toml")

    result = command_setup(restart=False)

    assert result == 1
    # No config file should be created
    assert not (tmp_path / "config.toml").exists()


def test_setup_returns_1_if_module_not_found(monkeypatch, tmp_path):
    """Test that setup returns 1 if echo-cancel module is not found."""
    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: True)
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", tmp_path / "config.toml")

    # Force is_macos to return False so we get to the module check
    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    # Mock glob to return no matches
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: [])

    result = command_setup(restart=False)

    assert result == 1
    # No config file should be created
    assert not (tmp_path / "config.toml").exists()


def test_setup_writes_pipewire_conf(monkeypatch, tmp_path):
    """Test that setup writes the PipeWire config file."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", tmp_path / "config.toml")
    # Mock glob to return a module
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    # Mock subprocess to avoid actually running systemctl
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0))
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.check_output", lambda *args, **kwargs: "claudechat_ec_source\nclaudechat_ec_sink\n")

    result = command_setup(restart=True)

    assert result == 0
    assert pw_conf_dir.exists()
    pw_conf = pw_conf_dir / "99-claudechat-echo-cancel.conf"
    assert pw_conf.exists()
    assert pw_conf.read_text() == PIPEWIRE_CONF


def test_setup_skips_pipewire_conf_rewrite_if_identical(monkeypatch, tmp_path):
    """Test that setup skips rewriting PipeWire config if content is identical."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    pw_conf_dir.mkdir(parents=True)
    pw_conf = pw_conf_dir / "99-claudechat-echo-cancel.conf"
    pw_conf.write_text(PIPEWIRE_CONF)
    original_mtime = pw_conf.stat().st_mtime

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf)
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0))
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.check_output", lambda *args, **kwargs: "claudechat_ec_source\nclaudechat_ec_sink\n")

    # Wait a tiny bit to ensure any mtime change would be detectable
    import time
    time.sleep(0.01)

    result = command_setup(restart=True)

    assert result == 0
    # Check that the file was not rewritten (mtime unchanged)
    assert pw_conf.stat().st_mtime == original_mtime


def test_setup_writes_config_keys(monkeypatch, tmp_path):
    """Test that setup writes the config keys to the [speech] section."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0))
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.check_output", lambda *args, **kwargs: "claudechat_ec_source\nclaudechat_ec_sink\n")

    result = command_setup(restart=True)

    assert result == 0
    assert config_path.exists()
    data = tomllib.loads(config_path.read_text())
    assert data["speech"]["capture_target"] == "claudechat_ec_source"
    assert data["speech"]["playback_target"] == "claudechat_ec_sink"
    assert data["speech"]["voice_barge_in"] is True


def test_setup_preserves_existing_config_keys(monkeypatch, tmp_path):
    """Test that setup preserves other config keys when writing the new ones."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[speech]\n'
        'tts_voice = "bm_fable"\n'
        'tts_speed = 1.1\n'
        '\n'
        '[hook]\n'
        'spoken_summaries = false\n'
    )

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0))
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.check_output", lambda *args, **kwargs: "claudechat_ec_source\nclaudechat_ec_sink\n")

    result = command_setup(restart=True)

    assert result == 0
    data = tomllib.loads(config_path.read_text())
    # New keys should be set
    assert data["speech"]["capture_target"] == "claudechat_ec_source"
    assert data["speech"]["playback_target"] == "claudechat_ec_sink"
    assert data["speech"]["voice_barge_in"] is True
    # Existing keys should be preserved
    assert data["speech"]["tts_voice"] == "bm_fable"
    assert data["speech"]["tts_speed"] == 1.1
    assert data["hook"]["spoken_summaries"] is False


def test_setup_returns_1_if_systemctl_fails(monkeypatch, tmp_path):
    """Test that setup returns 1 if systemctl restart fails."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    # Mock systemctl to fail
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=1))

    result = command_setup(restart=True)

    assert result == 1


def test_setup_returns_1_if_nodes_do_not_appear(monkeypatch, tmp_path):
    """Test that setup returns 1 if echo-cancel nodes do not appear after restart."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", lambda *args, **kwargs: MagicMock(returncode=0))
    # Mock check_output to return output without the expected nodes
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.check_output", lambda *args, **kwargs: "some_other_node\n")

    result = command_setup(restart=True)

    assert result == 1


@pytest.mark.parametrize("restart_value", [True, False])
def test_setup_without_restart_skips_systemctl(monkeypatch, tmp_path, restart_value):
    """Test that setup with restart=False does not run systemctl."""
    pw_conf_dir = tmp_path / ".config" / "pipewire" / "pipewire.conf.d"
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr("claudechat.cli.echocancel.is_macos", lambda: False)
    monkeypatch.setattr("claudechat.cli.echocancel.conf_path", lambda: pw_conf_dir / "99-claudechat-echo-cancel.conf")
    monkeypatch.setattr("claudechat.cli.echocancel.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("claudechat.cli.echocancel.glob.glob", lambda pattern: ["/usr/lib/x86_64-linux-gnu/pipewire-0.3/libpipewire-module-echo-cancel.so"])

    subprocess_run_mock = MagicMock()
    monkeypatch.setattr("claudechat.cli.echocancel.subprocess.run", subprocess_run_mock)

    result = command_setup(restart=restart_value)

    # Should not call subprocess.run when restart=False
    if not restart_value:
        subprocess_run_mock.assert_not_called()
        assert result == 0  # Should succeed anyway (just writes config)
    else:
        subprocess_run_mock.assert_called()
