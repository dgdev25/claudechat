from __future__ import annotations

from typing import Callable

import numpy as np


class SpeechGate:
    """Detects when the user starts and stops talking, from streamed PCM.

    Implements a state machine: waiting -> speech -> end. Transitions depend on
    sustained speech above threshold and trailing silence duration.
    """

    # Silero VAD fixed window size
    _WINDOW_SIZE = 512
    # Silero VAD context size for LSTM
    _CONTEXT_SIZE = 64

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        silence_ms: int = 700,
        min_speech_ms: int = 200,
        probability_fn: Callable[[np.ndarray], float] | None = None,
    ) -> None:
        """Initialize speech gate.

        Args:
            sample_rate: Audio sample rate in Hz.
            threshold: Speech probability threshold (0..1). Windows with
                probability >= threshold count as speech.
            silence_ms: Continuous silence duration (ms) to end a turn.
            min_speech_ms: Minimum cumulative speech duration (ms) to reach
                "speech" state.
            probability_fn: Function mapping one 512-sample float32 window to
                probability 0..1. When None, lazily load the real Silero model
                from faster_whisper on first feed().
        """
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._silence_samples = int(sample_rate * silence_ms / 1000)
        self._min_speech_samples = int(sample_rate * min_speech_ms / 1000)
        self._probability_fn = probability_fn
        self._buffer = np.array([], dtype=np.float32)
        self._state = "waiting"
        self._cumulative_speech_samples = 0
        self._trailing_silence_samples = 0
        self._model = None
        self._h = None  # LSTM hidden state
        self._c = None  # LSTM cell state
        self._history = None  # 64-sample context buffer

    @property
    def state(self) -> str:
        """Current state: "waiting" | "speech" | "end"."""
        return self._state

    def feed(self, pcm: bytes) -> str:
        """Process PCM audio and return current state.

        Args:
            pcm: 16-bit little-endian mono PCM at sample_rate.

        Returns:
            "waiting" - no sustained speech yet, or speech ended.
            "speech" - speech detected and sustained above min_speech_ms.
            "end" - turn ended (speech + sufficient trailing silence).
        """
        if not pcm:
            return self._state

        # Convert 16-bit PCM to float32 [-1, 1]
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0

        # Append to buffer
        self._buffer = np.concatenate([self._buffer, audio])

        # Get probability function (lazy load if needed)
        prob_fn = self._probability_fn
        if prob_fn is None:
            prob_fn = self._get_silero_probability_fn()

        # Process complete windows
        while len(self._buffer) >= self._WINDOW_SIZE:
            window = self._buffer[:self._WINDOW_SIZE]
            self._buffer = self._buffer[self._WINDOW_SIZE:]

            prob = prob_fn(window)

            # Update state based on probability and threshold
            if prob >= self.threshold:
                # Speech window
                self._cumulative_speech_samples += self._WINDOW_SIZE
                self._trailing_silence_samples = 0

                if (
                    self._state == "waiting"
                    and self._cumulative_speech_samples >= self._min_speech_samples
                ):
                    self._state = "speech"
            else:
                # Silence window
                self._trailing_silence_samples += self._WINDOW_SIZE

                if (
                    self._state == "speech"
                    and self._trailing_silence_samples >= self._silence_samples
                ):
                    self._state = "end"

        return self._state

    def reset(self) -> None:
        """Reset to waiting state. Clears cumulative counters and buffer."""
        self._state = "waiting"
        self._cumulative_speech_samples = 0
        self._trailing_silence_samples = 0
        self._buffer = np.array([], dtype=np.float32)

    def _get_silero_probability_fn(self) -> Callable[[np.ndarray], float]:
        """Load Silero VAD model and return probability function.

        The function maintains LSTM state (h, c) across windows for proper
        contextualization and accuracy.
        """
        if self._model is None:
            from faster_whisper.vad import get_vad_model

            self._model = get_vad_model()
            # Initialize model LSTM state
            self._h = np.zeros((1, 1, 128), dtype="float32")
            self._c = np.zeros((1, 1, 128), dtype="float32")
            # Keep history for context (64 samples)
            self._history = np.zeros(self._CONTEXT_SIZE, dtype="float32")

        def compute_probability(window: np.ndarray) -> float:
            """Compute speech probability for one 512-sample window."""
            # Prepare input: [64-sample context | 512-sample window]
            audio = np.concatenate([self._history, window]).reshape(1, -1)

            # Run model session with current LSTM state
            output, self._h, self._c = self._model.session.run(
                None,
                {"input": audio, "h": self._h, "c": self._c},
            )

            # Update history for next window (last 64 samples of current window)
            self._history = window[-self._CONTEXT_SIZE :]

            # Return speech probability (output is shape (1,) for single window)
            return float(output[0])

        return compute_probability
