from __future__ import annotations

import numpy as np

from claudechat.config import Config
from claudechat.speech.models import KOKORO_MODEL, KOKORO_VOICES, ensure_model


class KokoroSynthesizer:
    """Local CPU speech synthesis. Measured real-time factor 0.168."""

    def __init__(self, config: Config) -> None:
        from kokoro_onnx import Kokoro

        model_path = ensure_model(KOKORO_MODEL, config.models_dir)
        voices_path = ensure_model(KOKORO_VOICES, config.models_dir)
        self._kokoro = Kokoro(str(model_path), str(voices_path))
        self._voice = config.tts_voice
        self._speed = config.tts_speed
        self.sample_rate = 24000

    def synthesize(self, text: str) -> tuple[bytes, int]:
        text = text.strip()
        if not text:
            return b"", self.sample_rate
        samples, rate = self._kokoro.create(
            text, voice=self._voice, speed=self._speed, lang="en-us"
        )
        self.sample_rate = rate
        clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
        return (clipped * 32767.0).astype("<i2").tobytes(), rate
