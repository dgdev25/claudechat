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
    summary_threshold_chars: int = 400
    spoken_summaries: bool = False
    max_recording_seconds: float = 60.0
    max_speech_seconds: float = 120.0
    hook_min_interval_seconds: float = 1.0
    debug_logging: bool = False
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

    cfg = Config(
        stt_model=speech.get("stt_model", Config.stt_model),
        tts_voice=speech.get("tts_voice", Config.tts_voice),
        tts_speed=float(speech.get("tts_speed", Config.tts_speed)),
        summary_threshold_chars=int(hook.get("summary_threshold_chars", Config.summary_threshold_chars)),
        spoken_summaries=bool(hook.get("spoken_summaries", Config.spoken_summaries)),
        max_recording_seconds=float(limits.get("max_recording_seconds", Config.max_recording_seconds)),
        max_speech_seconds=float(limits.get("max_speech_seconds", Config.max_speech_seconds)),
        hook_min_interval_seconds=float(limits.get("hook_min_interval_seconds", Config.hook_min_interval_seconds)),
        debug_logging=bool(data.get("debug_logging", Config.debug_logging)),
    )

    _check_clean("tts_voice", cfg.tts_voice)
    _check_clean("stt_model", cfg.stt_model)
    if not 0.5 <= cfg.tts_speed <= 2.0:
        raise ValueError("tts_speed must be between 0.5 and 2.0")
    if not 1.0 <= cfg.max_recording_seconds <= 300.0:
        raise ValueError("max_recording_seconds must be between 1 and 300")
    return cfg
