#!/usr/bin/env python3
"""Report the PRD section 4 metrics so regressions are visible."""
from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path

from claudechat.claude.runner import ClaudeRunner, VOICE_SYSTEM_PROMPT
from claudechat.config import Config
from claudechat.speech.synthesizer import KokoroSynthesizer
from claudechat.speech.transcriber import WhisperTranscriber
from claudechat.text.chunk import SentenceChunker
from claudechat.text.strip import SpeechStripper


def main() -> None:
    config = Config()
    if models_dir := os.environ.get("CLAUDECHAT_MODELS_DIR"):
        config = replace(config, models_dir=Path(models_dir))
    sentence = "I looked at the file and found three problems with the login handler."

    synth = KokoroSynthesizer(config)
    start = time.perf_counter()
    pcm, rate = synth.synthesize(sentence)
    tts_seconds = time.perf_counter() - start
    audio_seconds = len(pcm) / 2 / rate
    print(f"TTS   wall={tts_seconds:.2f}s audio={audio_seconds:.2f}s rtf={tts_seconds / audio_seconds:.3f}")

    transcriber = WhisperTranscriber(config)
    transcriber.transcribe(pcm[:rate], rate)
    start = time.perf_counter()
    heard = transcriber.transcribe(pcm, rate)
    stt_seconds = time.perf_counter() - start
    print(f"STT   wall={stt_seconds:.2f}s rtf={stt_seconds / audio_seconds:.3f}")
    print(f"      heard: {heard}")

    runner = ClaudeRunner(config, internal_token="benchmark")
    stripper, chunker = SpeechStripper(), SentenceChunker()
    start = time.perf_counter()
    first_chunk = None
    for event in runner.stream("Explain what a race condition is, briefly.", VOICE_SYSTEM_PROMPT):
        if event.kind == "text":
            for _ in chunker.feed(stripper.feed(event.text)):
                first_chunk = time.perf_counter() - start
                break
        if first_chunk is not None:
            break
    if first_chunk is None:
        # Match Conversation's normal end-of-stream handling for replies without newlines.
        for _ in chunker.feed(stripper.flush()) + chunker.flush():
            first_chunk = time.perf_counter() - start
            break
    runner.cancel()
    if first_chunk is None:
        print("CLAUDE first speakable sentence=unavailable")
        print("TOTAL to first audio=unavailable (target ≤ 3.5s)")
        return
    print(f"CLAUDE first speakable sentence={first_chunk:.2f}s")
    print(f"TOTAL to first audio ≈ {stt_seconds + first_chunk + tts_seconds:.2f}s (target ≤ 3.5s)")


if __name__ == "__main__":
    main()
