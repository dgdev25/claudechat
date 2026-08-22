#!/usr/bin/env python3
"""Register the claudechat Stop hook in ~/.claude/settings.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"


def install_hook(settings_path: Path, hook_path: Path) -> None:
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, ValueError):
            raise SystemExit(f"{settings_path} is not valid JSON; refusing to overwrite")

    command = f"{sys.executable} {hook_path}"
    hooks = data.setdefault("hooks", {})
    stop_groups = hooks.setdefault("Stop", [])

    for group in stop_groups:
        for entry in group.get("hooks", []):
            if hook_path.name in entry.get("command", ""):
                entry["command"] = command
                settings_path.write_text(json.dumps(data, indent=2))
                return

    stop_groups.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": command, "timeout": 10}],
        }
    )
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    hook = Path(__file__).resolve().parent / "claudechat_hook.py"
    install_hook(DEFAULT_SETTINGS, hook)
    print(f"registered Stop hook: {hook}")
