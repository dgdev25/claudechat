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
