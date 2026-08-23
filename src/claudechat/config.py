from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "claudechat" / "config.toml"


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / "claudechat"
    return Path.home() / ".cache" / "claudechat" / "run"


@dataclass(frozen=True)
class Config:
    stt_model: str = "base.en"
    tts_voice: str = "af_heart"
    tts_speed: float = 1.0
    claude_model: str = "sonnet"
    summary_model: str = "haiku"
    summary_threshold_chars: int = 400
    spoken_summaries: bool = False
    max_recording_seconds: float = 60.0
    max_speech_seconds: float = 120.0
    hook_min_interval_seconds: float = 1.0
    stt_cpu_threads: int = 8
    first_chunk_min_chars: int = 10
    first_chunk_max_words: int = 30
    debug_logging: bool = False
    hands_free: bool = False
    thinking_cue: bool = True
    vad_silence_ms: int = 700
    vad_threshold: float = 0.5
    voice_replies: bool = False
    voice_reply_window_seconds: float = 6.0
    voice_barge_in: bool = False
    capture_target: str = ""
    barge_capture_target: str = ""
    playback_target: str = ""
    focus_cwd: str = ""
    stt_vocabulary: str = ""
    models_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "claudechat" / "models")
    runtime_dir: Path = field(default_factory=_runtime_dir)


def _check_clean(name: str, value: str) -> None:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{name} contains control characters")


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    data: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            data = tomllib.load(fh)

    speech = data.get("speech", {})
    hook = data.get("hook", {})
    limits = data.get("limits", {})
    claude = data.get("claude", {})

    cfg = Config(
        stt_model=speech.get("stt_model", Config.stt_model),
        tts_voice=speech.get("tts_voice", Config.tts_voice),
        tts_speed=float(speech.get("tts_speed", Config.tts_speed)),
        claude_model=claude.get("claude_model", Config.claude_model),
        summary_model=claude.get("summary_model", Config.summary_model),
        summary_threshold_chars=int(hook.get("summary_threshold_chars", Config.summary_threshold_chars)),
        spoken_summaries=bool(hook.get("spoken_summaries", Config.spoken_summaries)),
        max_recording_seconds=float(limits.get("max_recording_seconds", Config.max_recording_seconds)),
        max_speech_seconds=float(limits.get("max_speech_seconds", Config.max_speech_seconds)),
        hook_min_interval_seconds=float(limits.get("hook_min_interval_seconds", Config.hook_min_interval_seconds)),
        stt_cpu_threads=int(speech.get("stt_cpu_threads", Config.stt_cpu_threads)),
        first_chunk_min_chars=int(speech.get("first_chunk_min_chars", Config.first_chunk_min_chars)),
        first_chunk_max_words=int(speech.get("first_chunk_max_words", Config.first_chunk_max_words)),
        debug_logging=bool(data.get("debug_logging", Config.debug_logging)),
        hands_free=bool(speech.get("hands_free", Config.hands_free)),
        thinking_cue=bool(speech.get("thinking_cue", Config.thinking_cue)),
        vad_silence_ms=int(speech.get("vad_silence_ms", Config.vad_silence_ms)),
        vad_threshold=float(speech.get("vad_threshold", Config.vad_threshold)),
        voice_replies=bool(hook.get("voice_replies", Config.voice_replies)),
        voice_reply_window_seconds=float(hook.get("voice_reply_window_seconds", Config.voice_reply_window_seconds)),
        voice_barge_in=bool(speech.get("voice_barge_in", Config.voice_barge_in)),
        capture_target=str(speech.get("capture_target", Config.capture_target)),
        barge_capture_target=str(speech.get("barge_capture_target", Config.barge_capture_target)),
        playback_target=str(speech.get("playback_target", Config.playback_target)),
        focus_cwd=str(hook.get("focus_cwd", Config.focus_cwd)),
        stt_vocabulary=str(speech.get("stt_vocabulary", Config.stt_vocabulary)),
    )

    _check_clean("tts_voice", cfg.tts_voice)
    _check_clean("stt_model", cfg.stt_model)
    _check_clean("claude_model", cfg.claude_model)
    _check_clean("summary_model", cfg.summary_model)
    _check_clean("capture_target", cfg.capture_target)
    _check_clean("barge_capture_target", cfg.barge_capture_target)
    _check_clean("playback_target", cfg.playback_target)
    _check_clean("focus_cwd", cfg.focus_cwd)
    _check_clean("stt_vocabulary", cfg.stt_vocabulary)
    if not 0.5 <= cfg.tts_speed <= 2.0:
        raise ValueError("tts_speed must be between 0.5 and 2.0")
    if not 1.0 <= cfg.max_recording_seconds <= 300.0:
        raise ValueError("max_recording_seconds must be between 1 and 300")
    if not 1 <= cfg.stt_cpu_threads <= 64:
        raise ValueError("stt_cpu_threads must be between 1 and 64")
    if not 1 <= cfg.first_chunk_min_chars <= 200:
        raise ValueError("first_chunk_min_chars must be between 1 and 200")
    if not 5 <= cfg.first_chunk_max_words <= 200:
        raise ValueError("first_chunk_max_words must be between 5 and 200")
    if not 200 <= cfg.vad_silence_ms <= 5000:
        raise ValueError("vad_silence_ms must be between 200 and 5000")
    if not 0.1 <= cfg.vad_threshold <= 0.95:
        raise ValueError("vad_threshold must be between 0.1 and 0.95")
    if not 2.0 <= cfg.voice_reply_window_seconds <= 30.0:
        raise ValueError("voice_reply_window_seconds must be between 2.0 and 30.0")
    if len(cfg.stt_vocabulary) > 800:
        raise ValueError("stt_vocabulary must not exceed 800 characters")
    return cfg
