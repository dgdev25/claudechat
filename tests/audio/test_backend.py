import pytest

from claudechat.audio import backend
from claudechat.audio.backend import AudioUnavailable, capture_command, playback_command


def _fake_which(available):
    return lambda name: f"/usr/bin/{name}" if name in available else None


def test_linux_uses_pipewire(monkeypatch):
    monkeypatch.setattr(backend.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backend.shutil, "which", _fake_which({"pw-cat", "pw-record"}))
    play = playback_command(24000)
    record = capture_command(16000)
    assert play[0].endswith("pw-cat")
    assert "--playback" in play and "--raw" in play
    assert "--rate=24000" in play
    assert record[0].endswith("pw-record")
    assert "--rate=16000" in record


def test_macos_prefers_sox(monkeypatch):
    monkeypatch.setattr(backend.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(backend.shutil, "which", _fake_which({"play", "rec"}))
    play = playback_command(24000)
    record = capture_command(16000)
    assert play[0].endswith("play")
    assert record[0].endswith("rec")
    # raw s16le mono, matching what every caller produces and expects
    for argv, rate in ((play, "24000"), (record, "16000")):
        assert "raw" in argv and "signed" in argv
        assert "16" in argv and "1" in argv
        assert rate in argv


def test_macos_falls_back_to_ffmpeg(monkeypatch):
    monkeypatch.setattr(backend.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(backend.shutil, "which", _fake_which({"ffplay", "ffmpeg"}))
    assert playback_command(24000)[0].endswith("ffplay")
    record = capture_command(16000)
    assert record[0].endswith("ffmpeg")
    assert "avfoundation" in record


def test_macos_without_tools_names_the_fix(monkeypatch):
    monkeypatch.setattr(backend.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(backend.shutil, "which", _fake_which(set()))
    for call in (playback_command, capture_command):
        with pytest.raises(AudioUnavailable) as excinfo:
            call(16000)
        assert "brew install sox" in str(excinfo.value)


def test_linux_without_tools_names_the_fix(monkeypatch):
    monkeypatch.setattr(backend.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backend.shutil, "which", _fake_which(set()))
    with pytest.raises(AudioUnavailable) as excinfo:
        playback_command(16000)
    assert "pipewire" in str(excinfo.value).lower()
