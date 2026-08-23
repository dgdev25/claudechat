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


def test_claude_model_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.claude_model == "sonnet"
    assert cfg.summary_model == "haiku"


def test_claude_model_from_config(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[claude]\nclaude_model = "opus"\nsummary_model = "sonnet"\n')
    cfg = load_config(p)
    assert cfg.claude_model == "opus"
    assert cfg.summary_model == "sonnet"


def test_rejects_control_characters_in_claude_model(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[claude]\nclaude_model = "son\\u0001net"\n')
    try:
        load_config(p)
    except ValueError as e:
        assert "claude_model" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_speech_config_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.stt_cpu_threads == 8
    assert cfg.first_chunk_min_chars == 10
    assert cfg.first_chunk_max_words == 30


def test_speech_config_from_file(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[speech]\nstt_cpu_threads = 16\nfirst_chunk_min_chars = 20\nfirst_chunk_max_words = 50\n')
    cfg = load_config(p)
    assert cfg.stt_cpu_threads == 16
    assert cfg.first_chunk_min_chars == 20
    assert cfg.first_chunk_max_words == 50


def test_rejects_stt_cpu_threads_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\nstt_cpu_threads = 0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "stt_cpu_threads" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[speech]\nstt_cpu_threads = 128\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "stt_cpu_threads" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_first_chunk_min_chars_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\nfirst_chunk_min_chars = 0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "first_chunk_min_chars" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[speech]\nfirst_chunk_min_chars = 300\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "first_chunk_min_chars" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_first_chunk_max_words_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\nfirst_chunk_max_words = 4\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "first_chunk_max_words" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[speech]\nfirst_chunk_max_words = 300\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "first_chunk_max_words" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_vad_config_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.hands_free is False
    assert cfg.thinking_cue is True
    assert cfg.vad_silence_ms == 700
    assert cfg.vad_threshold == 0.5


def test_vad_config_from_file(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[speech]\nhands_free = true\nthinking_cue = false\nvad_silence_ms = 1000\nvad_threshold = 0.7\n')
    cfg = load_config(p)
    assert cfg.hands_free is True
    assert cfg.thinking_cue is False
    assert cfg.vad_silence_ms == 1000
    assert cfg.vad_threshold == 0.7


def test_rejects_vad_silence_ms_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\nvad_silence_ms = 100\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "vad_silence_ms" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[speech]\nvad_silence_ms = 10000\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "vad_silence_ms" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_vad_threshold_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[speech]\nvad_threshold = 0.05\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "vad_threshold" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[speech]\nvad_threshold = 1.0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "vad_threshold" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_voice_replies_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.voice_replies is False
    assert cfg.voice_reply_window_seconds == 6.0


def test_voice_replies_from_config(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[hook]\nvoice_replies = true\nvoice_reply_window_seconds = 10.0\n")
    cfg = load_config(p)
    assert cfg.voice_replies is True
    assert cfg.voice_reply_window_seconds == 10.0


def test_rejects_voice_reply_window_seconds_out_of_range(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[hook]\nvoice_reply_window_seconds = 1.0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "voice_reply_window_seconds" in str(e)
    else:
        raise AssertionError("expected ValueError")

    p.write_text("[hook]\nvoice_reply_window_seconds = 40.0\n")
    try:
        load_config(p)
    except ValueError as e:
        assert "voice_reply_window_seconds" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_focus_cwd_defaults_to_empty(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.focus_cwd == ""


def test_focus_cwd_from_config(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[hook]\nfocus_cwd = "/home/user/project"\n')
    cfg = load_config(p)
    assert cfg.focus_cwd == "/home/user/project"


def test_rejects_control_characters_in_focus_cwd(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[hook]\nfocus_cwd = "/home/user\\u0001project"\n')
    try:
        load_config(p)
    except ValueError as e:
        assert "focus_cwd" in str(e)
    else:
        raise AssertionError("expected ValueError")
