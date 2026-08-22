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
