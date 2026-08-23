from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

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


def test_initial_prompt_includes_base_and_user_vocabulary():
    """Test that transcribe passes initial_prompt with base and user vocabulary."""
    config = Config(stt_vocabulary="ruflo, sf")

    # Create a mock WhisperModel
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "test"
    mock_model.transcribe.return_value = ([mock_segment], None)

    # Create a mock faster_whisper module with WhisperModel
    mock_faster_whisper = MagicMock()
    mock_faster_whisper.WhisperModel = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"faster_whisper": mock_faster_whisper}):
        transcriber = WhisperTranscriber(config)
        # Call transcribe with dummy audio (will be processed but won't use the mock's actual logic)
        pcm = b"\x00\x01" * 100  # Minimal audio buffer
        transcriber.transcribe(pcm, 16000)

    # Verify transcribe was called with initial_prompt
    assert mock_model.transcribe.called
    call_kwargs = mock_model.transcribe.call_args[1]
    assert "initial_prompt" in call_kwargs
    prompt = call_kwargs["initial_prompt"]

    # Verify prompt contains base vocabulary terms
    assert "ONNX" in prompt
    assert "Claude" in prompt
    assert "pyproject" in prompt

    # Verify prompt contains user vocabulary terms
    assert "ruflo" in prompt
    assert "sf" in prompt

    # Verify prompt format starts with "Glossary: " and ends with "."
    assert prompt.startswith("Glossary: ")
    assert prompt.endswith(".")


def test_initial_prompt_with_empty_vocabulary():
    """Test that transcribe passes initial_prompt even when user vocabulary is empty."""
    config = Config(stt_vocabulary="")

    # Create a mock WhisperModel
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "test"
    mock_model.transcribe.return_value = ([mock_segment], None)

    # Create a mock faster_whisper module with WhisperModel
    mock_faster_whisper = MagicMock()
    mock_faster_whisper.WhisperModel = MagicMock(return_value=mock_model)

    with patch.dict(sys.modules, {"faster_whisper": mock_faster_whisper}):
        transcriber = WhisperTranscriber(config)
        pcm = b"\x00\x01" * 100
        transcriber.transcribe(pcm, 16000)

    # Verify transcribe was called with initial_prompt
    assert mock_model.transcribe.called
    call_kwargs = mock_model.transcribe.call_args[1]
    assert "initial_prompt" in call_kwargs
    prompt = call_kwargs["initial_prompt"]

    # Verify prompt contains only base vocabulary
    assert "ONNX" in prompt
    assert "Claude" in prompt
    assert prompt.startswith("Glossary: ")
    assert prompt.endswith(".")
