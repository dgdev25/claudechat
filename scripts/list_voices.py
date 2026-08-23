#!/usr/bin/env python3
"""List every voice the installed Kokoro model provides, grouped by accent."""
from __future__ import annotations

from claudechat.config import load_config
from claudechat.speech.models import KOKORO_MODEL, KOKORO_VOICES, ensure_model

ACCENTS = {
    "af_": "American female", "am_": "American male",
    "bf_": "British female", "bm_": "British male",
    "ef_": "Spanish female", "em_": "Spanish male",
    "ff_": "French female",
    "hf_": "Hindi female", "hm_": "Hindi male",
    "if_": "Italian female", "im_": "Italian male",
    "jf_": "Japanese female", "jm_": "Japanese male",
    "pf_": "Portuguese female", "pm_": "Portuguese male",
    "zf_": "Chinese female", "zm_": "Chinese male",
}


def main() -> None:
    from kokoro_onnx import Kokoro

    config = load_config()
    kokoro = Kokoro(
        str(ensure_model(KOKORO_MODEL, config.models_dir)),
        str(ensure_model(KOKORO_VOICES, config.models_dir)),
    )
    voices = sorted(kokoro.get_voices())
    print(f"{len(voices)} voices. Current: {config.tts_voice}\n")
    for prefix, label in ACCENTS.items():
        matching = [v for v in voices if v.startswith(prefix)]
        if matching:
            print(f"{label:18s} {', '.join(matching)}")


if __name__ == "__main__":
    main()
