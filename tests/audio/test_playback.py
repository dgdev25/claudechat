import time

from claudechat.audio.playback import Playback


def test_cancel_stops_playback_promptly():
    pcm = b"\x00\x00" * 16000 * 5
    player = Playback(sample_rate=16000)
    player.play(pcm)
    assert player.is_playing()

    start = time.perf_counter()
    player.cancel()
    elapsed = time.perf_counter() - start

    assert elapsed < 0.3
    assert not player.is_playing()


def test_cancel_is_safe_when_idle():
    Playback(sample_rate=16000).cancel()


def test_empty_audio_is_ignored():
    player = Playback(sample_rate=16000)
    player.play(b"")
    assert not player.is_playing()
