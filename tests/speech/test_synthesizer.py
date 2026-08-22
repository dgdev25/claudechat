from pathlib import Path

import pytest

from claudechat.config import Config
from claudechat.speech.synthesizer import KokoroSynthesizer


@pytest.fixture(scope="module")
def synth():
    return KokoroSynthesizer(Config(models_dir=Path("/tmp/claudechat-models")))


@pytest.mark.slow
def test_produces_audio_of_plausible_length(synth):
    pcm, rate = synth.synthesize("This is a test of the speech system.")
    assert rate >= 16000
    seconds = len(pcm) / 2 / rate
    assert 1.0 < seconds < 6.0


@pytest.mark.slow
def test_empty_text_produces_no_audio(synth):
    pcm, _ = synth.synthesize("   ")
    assert pcm == b""


@pytest.mark.slow
def test_output_is_16bit_mono(synth):
    pcm, _ = synth.synthesize("Short.")
    assert len(pcm) % 2 == 0
