import tomllib
from claudechat.config import load_config, _check_clean


def test_defaults_are_used_when_no_file_exists(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.stt_model == "base.en"
    assert cfg.tts_voice == "af_heart"
    assert cfg.spoken_summaries is False          # off by default, security review
    assert cfg.max_recording_seconds == 60.0


def test_file_values_override_defaults(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[speech]\nstt_model = "tiny.en"\ntts_speed = 1.2\n')
    cfg = load_config(p)
    assert cfg.stt_model == "tiny.en"
    assert cfg.tts_speed == 1.2
    assert cfg.tts_voice == "af_heart"            # untouched default


def test_rejects_out_of_range_speed(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\ntts_speed = 99.0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "tts_speed" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_control_characters_in_config_file(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[speech]\ntts_voice = "af_h\\u0001eart"\n')
    try:
        load_config(p)
    except ValueError as e:
        assert "tts_voice" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_control_characters_in_voice_name(tmp_path):
    # Unit test for validation helper
    try:
        _check_clean("tts_voice", "af_h\x01eart")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
