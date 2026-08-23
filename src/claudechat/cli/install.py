"""One-command setup: the Claude Code Stop hook plus a systemd user service.

Both are reversible and both are printed before they are written, because they
change the user's environment rather than this project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "claudechat.service"

UNIT_TEMPLATE = """[Unit]
Description=claudechat speech daemon
After=default.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def _install_unit(project_root: Path) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv not found on PATH; cannot write a service unit")
    exec_start = f"{uv} run --project {project_root} claudechat serve"
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(UNIT_TEMPLATE.format(exec_start=exec_start))
    return UNIT_PATH


def _install_hook(project_root: Path) -> str:
    sys.path.insert(0, str(project_root / "scripts"))
    from install_hook import install_hook  # type: ignore[import-not-found]

    hook = project_root / "scripts" / "claudechat_hook.py"
    install_hook(SETTINGS_PATH, hook)
    return str(hook)


def command_install() -> int:
    project_root = Path(__file__).resolve().parents[3]

    hook = _install_hook(project_root)
    print(f"registered Stop hook   {hook}")
    print(f"                    in {SETTINGS_PATH}")

    unit = _install_unit(project_root)
    print(f"wrote service unit     {unit}")

    for args in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "claudechat"],
    ):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  {' '.join(args)} failed: {result.stderr.strip()[:120]}", file=sys.stderr)
            print("  start it by hand with: systemctl --user start claudechat", file=sys.stderr)
            break
    else:
        print("service enabled and started")

    print()
    print("Speech is OFF by default. Turn it on with:  claudechat on")
    print("Check anything with:                        claudechat status")
    print("To undo:  systemctl --user disable --now claudechat")
    print(f"          and remove the Stop hook from {SETTINGS_PATH}")
    return 0
