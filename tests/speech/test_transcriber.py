from pathlib import Path

import pytest

from claudechat.config import Config
from claudechat.speech.synthesizer import KokoroSynthesizer
from claudechat.speech.transcriber import WhisperTranscriber


@pytest.mark.slow
def test_round_trip_speech_to_text():
    spoken = "The quick brown fox jumps over the lazy dog."
    config = Config(models_dir=Path("/tmp/claudechat-models"))
    pcm, rate = KokoroSynthesizer(config).synthesize(spoken)
    heard = WhisperTranscriber(config).transcribe(pcm, rate)
    normalised = heard.lower().strip().rstrip(".")
    assert "quick brown fox" in normalised
    assert "lazy dog" in normalised


@pytest.mark.slow
def test_silence_transcribes_to_empty():
    config = Config(models_dir=Path("/tmp/claudechat-models"))
    assert WhisperTranscriber(config).transcribe(b"\x00\x00" * 16000, 16000).strip() == ""
