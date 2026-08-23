import tomllib

from claudechat.cli.daemon import _is_enabled, _set_spoken_summaries


def test_sets_the_flag_when_no_config_exists(tmp_path):
    path = tmp_path / "config.toml"
    _set_spoken_summaries(True, path)
    assert _is_enabled(path) is True
    assert tomllib.loads(path.read_text())["hook"]["spoken_summaries"] is True


def test_toggling_preserves_every_other_setting(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[speech]\n'
        'tts_voice = "bm_fable"\n'
        'tts_speed = 1.1\n'
        '\n'
        '[hook]\n'
        'spoken_summaries = false\n'
        'summary_threshold_chars = 400\n'
    )
    _set_spoken_summaries(True, path)
    data = tomllib.loads(path.read_text())
    assert data["hook"]["spoken_summaries"] is True
    assert data["speech"]["tts_voice"] == "bm_fable"        # untouched
    assert data["speech"]["tts_speed"] == 1.1               # untouched
    assert data["hook"]["summary_threshold_chars"] == 400   # untouched


def test_round_trips_off_and_on(tmp_path):
    path = tmp_path / "config.toml"
    _set_spoken_summaries(True, path)
    _set_spoken_summaries(False, path)
    assert _is_enabled(path) is False
    _set_spoken_summaries(True, path)
    assert _is_enabled(path) is True


def test_comments_survive_a_toggle(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('# my settings\n[hook]\nspoken_summaries = false\n')
    _set_spoken_summaries(True, path)
    assert "# my settings" in path.read_text()


def test_focus_writes_the_key(tmp_path):
    """GATE 2f: focus command writes focus_cwd with the current directory."""
    from claudechat.cli.daemon import command_focus
    import os

    path = tmp_path / "config.toml"
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        command_focus(path=path)
        data = tomllib.loads(path.read_text())
        assert data["hook"]["focus_cwd"] == str(tmp_path)
    finally:
        os.chdir(original_cwd)


def test_focus_off_clears_the_key(tmp_path):
    """GATE 2f: focus off command clears focus_cwd."""
    from claudechat.cli.daemon import command_focus
    import os

    path = tmp_path / "config.toml"
    path.write_text('[hook]\nfocus_cwd = "/some/path"\n')
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        command_focus("off", path=path)
        data = tomllib.loads(path.read_text())
        assert data["hook"]["focus_cwd"] == ""
    finally:
        os.chdir(original_cwd)


def test_focus_preserves_other_keys(tmp_path):
    """GATE 2f: focus command preserves other settings in the config."""
    from claudechat.cli.daemon import command_focus
    import os

    path = tmp_path / "config.toml"
    path.write_text(
        '[speech]\ntts_voice = "bm_fable"\n'
        '[hook]\nspoken_summaries = true\nsummary_threshold_chars = 500\n'
    )
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        command_focus(path=path)
        data = tomllib.loads(path.read_text())
        assert data["speech"]["tts_voice"] == "bm_fable"
        assert data["hook"]["spoken_summaries"] is True
        assert data["hook"]["summary_threshold_chars"] == 500
        assert data["hook"]["focus_cwd"] == str(tmp_path)
    finally:
        os.chdir(original_cwd)


def test_status_shows_voice_barge_in(tmp_path, monkeypatch, capsys):
    """Test that status command shows voice_barge_in setting."""
    from claudechat.cli.daemon import command_toggle
    from claudechat.config import Config

    # Monkeypatch load_config to return a config with voice_barge_in = True
    def mock_load_config():
        return Config(voice_barge_in=True, tts_voice="bm_fable", spoken_summaries=False)

    monkeypatch.setattr("claudechat.cli.daemon.load_config", mock_load_config)

    result = command_toggle("status")

    assert result == 0
    captured = capsys.readouterr()
    assert "voice barge-in: on" in captured.out


def test_status_shows_voice_barge_in_off(tmp_path, monkeypatch, capsys):
    """Test that status command shows voice_barge_in as off when disabled."""
    from claudechat.cli.daemon import command_toggle
    from claudechat.config import Config

    # Monkeypatch load_config to return a config with voice_barge_in = False
    def mock_load_config():
        return Config(voice_barge_in=False, tts_voice="bm_fable", spoken_summaries=False)

    monkeypatch.setattr("claudechat.cli.daemon.load_config", mock_load_config)

    result = command_toggle("status")

    assert result == 0
    captured = capsys.readouterr()
    assert "voice barge-in: off" in captured.out
