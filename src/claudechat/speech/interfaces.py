from __future__ import annotations

from typing import Protocol


class Transcriber(Protocol):
    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Return the text spoken in 16-bit little-endian mono PCM."""


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> tuple[bytes, int]:
        """Return (16-bit little-endian mono PCM, sample_rate) for text."""
