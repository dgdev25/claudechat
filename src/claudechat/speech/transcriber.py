from __future__ import annotations

import numpy as np

from claudechat.config import Config

_BASE_VOCABULARY = (
    "Claude, Claude Code, claudechat, Anthropic, Python, pyproject, ONNX, "
    "PipeWire, Whisper, Kokoro, VAD, barge-in, daemon, config, repo, commit, "
    "GitHub, API, CLI, TOML, JSON, README, backend, frontend, latency, async"
)


class WhisperTranscriber:
    """Local CPU transcription. base.en measured at 0.21 s for a 3.67 s clip."""

    def __init__(self, config: Config) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            config.stt_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=config.stt_cpu_threads,
        )

        # Build initial prompt for vocabulary biasing
        terms = [t.strip() for t in _BASE_VOCABULARY.split(",")]
        if config.stt_vocabulary:
            user_terms = [t.strip() for t in config.stt_vocabulary.split(",")]
            terms.extend(user_terms)
        self._initial_prompt = "Glossary: " + ", ".join(terms) + "."

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        if not pcm:
            return ""
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if sample_rate != 16000:
            audio = self._resample(audio, sample_rate, 16000)
        segments, _ = self._model.transcribe(
            audio, beam_size=1, language="en", initial_prompt=self._initial_prompt
        )
        return "".join(segment.text for segment in segments).strip()

    @staticmethod
    def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate == target_rate or audio.size == 0:
            return audio
        count = int(round(audio.size * target_rate / source_rate))
        source_positions = np.linspace(0.0, audio.size - 1, num=audio.size)
        target_positions = np.linspace(0.0, audio.size - 1, num=count)
        return np.interp(target_positions, source_positions, audio).astype(np.float32)
