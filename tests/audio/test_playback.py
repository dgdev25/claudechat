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


def test_player_process_survives_startup():
    """Catch a bad player invocation.

    The original command sent raw PCM to `pw-play -`, which rejects it via
    libsndfile ("Format not recognised") and exits rc=1. Nothing noticed,
    because stderr went to /dev/null and is_playing() was asserted instantly —
    the process had not died yet. Audio never actually played.

    Silence is used so the test is inaudible; the defect was in argument
    parsing, which fails regardless of content.
    """
    import time

    pcm = b"\x00\x00" * 16000 * 3          # three seconds of silence
    player = Playback(sample_rate=16000)
    try:
        player.play(pcm)
        time.sleep(0.4)                    # let a bad invocation die first
        assert player.is_playing(), "player exited during startup — bad arguments?"
    finally:
        player.cancel()
