from __future__ import annotations

import pytest

import numpy as np

from claudechat.audio.vad import SpeechGate


def pcm_speech(num_samples: int) -> bytes:
    """Generate non-zero PCM (speech)."""
    # 16-bit little-endian: b"\x01\x00" = 1 (very quiet tone)
    return b"\x01\x00" * num_samples


def pcm_silence(num_samples: int) -> bytes:
    """Generate zero PCM (silence)."""
    return b"\x00\x00" * num_samples


def prob_fn(window: np.ndarray) -> float:
    """Test probability function: keys off audio content.

    Returns 0.9 for non-zero windows, 0.1 for all-zero windows.
    """
    if np.any(window != 0):
        return 0.9
    return 0.1


def test_silence_only_stays_waiting():
    """Silence-only input stays in waiting state."""
    gate = SpeechGate(probability_fn=prob_fn)
    # Feed 2 seconds of silence
    for _ in range(4):
        state = gate.feed(pcm_silence(8000))
    assert state == "waiting"


def test_short_speech_stays_waiting():
    """Speech shorter than min_speech_ms stays in waiting state."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        probability_fn=prob_fn,
    )
    # Feed 100 ms of speech (16000 * 0.1 = 1600 samples)
    state = gate.feed(pcm_speech(1600))
    assert state == "waiting"


def test_sustained_speech_reaches_speech():
    """Sustained speech reaches speech state."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        probability_fn=prob_fn,
    )
    # Feed 300 ms of speech (16000 * 0.3 = 4800 samples)
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"


def test_speech_then_silence_reaches_end():
    """Speech followed by sufficient silence reaches end state."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        silence_ms=700,
        probability_fn=prob_fn,
    )
    # Feed 300 ms of speech
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"

    # Feed 800 ms of silence (enough to end)
    state = gate.feed(pcm_silence(12800))
    assert state == "end"


def test_short_silence_gap_does_not_end():
    """A short silence gap inside speech does not end the turn."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        silence_ms=700,
        probability_fn=prob_fn,
    )
    # Feed 300 ms of speech
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"

    # Feed 300 ms of silence (too short to end)
    state = gate.feed(pcm_silence(4800))
    assert state == "speech"  # Still in speech

    # Feed more speech
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"


def test_reset_returns_to_waiting():
    """reset() returns to waiting state."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        probability_fn=prob_fn,
    )
    # Reach speech state
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"

    # Reset
    gate.reset()
    assert gate._state == "waiting"

    # Verify ready to detect speech again
    state = gate.feed(pcm_speech(4800))
    assert state == "speech"


def test_end_state_persists_until_reset():
    """End state persists until reset()."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        silence_ms=700,
        probability_fn=prob_fn,
    )
    # Reach end state
    gate.feed(pcm_speech(4800))
    gate.feed(pcm_silence(12800))
    assert gate._state == "end"

    # Feed more silence; should stay in end
    state = gate.feed(pcm_silence(4800))
    assert state == "end"

    # Feed speech; should still be end
    state = gate.feed(pcm_speech(4800))
    assert state == "end"


def test_buffer_handles_arbitrary_pcm_sizes():
    """Buffer correctly handles arbitrary-size PCM chunks.

    SpeechGate buffers internally and processes in 512-sample windows,
    independent of input chunk size.
    """
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=200,
        probability_fn=prob_fn,
    )
    # Feed speech in many small chunks
    for _ in range(30):  # 30 * 160 = 4800 samples total
        state = gate.feed(pcm_speech(160))
    assert state == "speech"


def test_cumulative_speech_tracking():
    """Cumulative speech is tracked correctly across multiple feed() calls."""
    gate = SpeechGate(
        sample_rate=16000,
        min_speech_ms=400,  # Need 6400 samples total
        probability_fn=prob_fn,
    )
    # Feed 256 ms of speech (4096 samples = 8 windows) - not enough
    state = gate.feed(pcm_speech(4096))
    assert state == "waiting"

    # Feed another 256 ms (total 8192 samples = 16 windows) - now reaches speech
    state = gate.feed(pcm_speech(4096))
    assert state == "speech"


def test_threshold_respected():
    """Only windows with probability >= threshold count as speech."""

    def prob_fn_variable(window: np.ndarray) -> float:
        """Return probability that varies based on content."""
        max_val = np.max(np.abs(window))
        # Map max value to probability
        return float(max_val)

    gate = SpeechGate(
        sample_rate=16000,
        threshold=0.5,
        min_speech_ms=200,
        probability_fn=prob_fn_variable,
    )

    # Create audio that will have low probability (small values)
    # 16-bit value of 100 -> float32 value of 100/32768 ≈ 0.003 (below threshold)
    quiet = np.array([100], dtype="<i2").tobytes()
    # Feed lots of quiet audio
    for _ in range(50):
        state = gate.feed(quiet * 512)
    assert state == "waiting"  # Probability stays below 0.5


@pytest.mark.live
def test_real_model_detects_silence():
    """Test with real Silero model: silence scores low.

    This test requires the silero_vad_v6.onnx asset to be present.
    It is marked @pytest.mark.live and skipped by default.
    """
    pytest.importorskip("faster_whisper")

    try:
        gate = SpeechGate(sample_rate=16000)
    except RuntimeError:
        pytest.skip("silero_vad_v6.onnx asset not found")

    # Feed pure silence
    state = gate.feed(pcm_silence(4000))
    # Silence should result in low probabilities, stay in waiting
    assert state == "waiting"


@pytest.mark.live
def test_real_model_processes_audio():
    """Test with real Silero model: can process audio without errors.

    This test requires the silero_vad_v6.onnx asset.
    Marked @pytest.mark.live and skipped by default.
    Verifies the model loads and processes audio, but does not assert
    specific classification results (VAD behavior depends on audio content).
    """
    pytest.importorskip("faster_whisper")

    try:
        gate = SpeechGate(
            sample_rate=16000,
            min_speech_ms=200,
        )
    except RuntimeError:
        pytest.skip("silero_vad_v6.onnx asset not found")

    # Generate a simple tone (440 Hz sine wave)
    sample_rate = 16000
    duration_s = 0.5
    freq = 440
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), False)
    tone = np.sin(2 * np.pi * freq * t)
    # Convert to 16-bit PCM
    pcm = (tone * 32767).astype("<i2").tobytes()

    # Feed tone; model should process without error
    # Result depends on model training, but should be one of the valid states
    state = gate.feed(pcm)
    assert state in ("waiting", "speech", "end")


def test_peak_probability_tracks_maximum():
    """peak_probability tracks the maximum probability seen across feeds."""
    gate = SpeechGate(
        sample_rate=16000,
        probability_fn=lambda w: 0.3,
    )
    assert gate.peak_probability == 0.0

    # Feed first chunk
    gate.feed(pcm_speech(1024))
    assert gate.peak_probability == 0.3

    # Feed second chunk (same probability)
    gate.feed(pcm_speech(1024))
    assert gate.peak_probability == 0.3

    # Create a gate with variable probability
    def prob_fn_variable(window: np.ndarray) -> float:
        max_val = np.max(np.abs(window))
        return float(max_val)

    gate2 = SpeechGate(
        sample_rate=16000,
        probability_fn=prob_fn_variable,
    )
    # Feed low-amplitude audio
    gate2.feed(b"\x01\x00" * 512)
    first_peak = gate2.peak_probability
    # Feed high-amplitude audio
    high_amp = np.array([32000], dtype="<i2").tobytes()
    gate2.feed(high_amp * 512)
    assert gate2.peak_probability >= first_peak


def test_peak_probability_resets():
    """peak_probability is zeroed by reset()."""
    gate = SpeechGate(
        sample_rate=16000,
        probability_fn=lambda w: 0.9,
    )
    gate.feed(pcm_speech(1024))
    assert gate.peak_probability == 0.9

    gate.reset()
    assert gate.peak_probability == 0.0


def test_windows_fed_counts_512_sample_windows():
    """windows_fed counts the number of 512-sample windows processed."""
    gate = SpeechGate(
        sample_rate=16000,
        probability_fn=prob_fn,
    )
    assert gate.windows_fed == 0

    # Feed 512 samples (1 window)
    gate.feed(pcm_speech(512))
    assert gate.windows_fed == 1

    # Feed 1024 samples (2 windows)
    gate.feed(pcm_speech(1024))
    assert gate.windows_fed == 3

    # Feed 512 samples (1 more window)
    gate.feed(pcm_speech(512))
    assert gate.windows_fed == 4


def test_windows_fed_resets():
    """windows_fed is zeroed by reset()."""
    gate = SpeechGate(
        sample_rate=16000,
        probability_fn=prob_fn,
    )
    gate.feed(pcm_speech(2048))
    assert gate.windows_fed == 4

    gate.reset()
    assert gate.windows_fed == 0
