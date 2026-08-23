import time
from dataclasses import replace

import pytest

from claudechat.audio.capture import Capture
from claudechat.config import Config


@pytest.mark.slow
def test_records_and_returns_pcm():
    capture = Capture(Config())
    capture.start()
    assert capture.is_recording()
    time.sleep(0.5)
    pcm = capture.stop()
    assert not capture.is_recording()
    assert len(pcm) > 0


@pytest.mark.slow
def test_stops_automatically_at_the_duration_limit():
    capture = Capture(replace(Config(), max_recording_seconds=1.0))
    capture.start()
    time.sleep(1.6)
    assert not capture.is_recording()
    assert len(capture.stop()) > 0


def test_stop_without_start_returns_empty():
    assert Capture(Config()).stop() == b""


def test_take_returns_queued_bytes_once():
    """Test that take() returns accumulated audio and clears it."""
    import io
    import subprocess

    capture = Capture(Config())

    # Monkeypatch subprocess.Popen to return canned audio
    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(b"A" * 4096 + b"B" * 4096 + b"C" * 4096)
            self.pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            pass

    original_popen = subprocess.Popen
    subprocess.Popen = FakeProcess  # type: ignore

    try:
        capture.start()
        # Give the reader thread time to read all blocks
        time.sleep(0.2)

        # First take() returns the accumulated blocks
        first = capture.take()
        assert len(first) == 4096 * 3
        assert first == b"A" * 4096 + b"B" * 4096 + b"C" * 4096

        # Second take() returns empty (no new blocks since first take)
        second = capture.take()
        assert second == b""

        # stop() still returns everything including taken blocks
        capture.stop()
    finally:
        subprocess.Popen = original_popen


def test_stop_returns_everything_including_taken():
    """Test that stop() returns all audio even if take() was called."""
    import io
    import subprocess

    capture = Capture(Config())

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.stdout = io.BytesIO(b"X" * 4096 + b"Y" * 4096)
            self.pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            pass

    original_popen = subprocess.Popen
    subprocess.Popen = FakeProcess  # type: ignore

    try:
        capture.start()
        time.sleep(0.1)

        # Take some audio
        first_take = capture.take()
        assert len(first_take) == 4096 * 2

        # stop() returns everything, including taken bytes
        all_audio = capture.stop()
        assert all_audio == b"X" * 4096 + b"Y" * 4096
    finally:
        subprocess.Popen = original_popen
