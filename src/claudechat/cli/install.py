"""Setup, in two independent pieces.

The Stop hook is what makes Claude Code speak; it is harmless on its own,
because the hook exits quietly when no daemon is listening. Autostart is a
separate, optional choice — some people want speech only in the sessions where
they ask for it, and a service that resurrects itself every login is the wrong
default for that.

    install            register the Stop hook only
    install --service  also install and enable the systemd user service
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


def install_service(project_root: Path) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv not found on PATH; cannot write a service unit")
    UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UNIT_PATH.write_text(
        UNIT_TEMPLATE.format(exec_start=f"{uv} run --project {project_root} claudechat serve")
    )
    return UNIT_PATH


def install_hook(project_root: Path) -> str:
    sys.path.insert(0, str(project_root / "scripts"))
    from install_hook import install_hook as register  # type: ignore[import-not-found]

    hook = project_root / "scripts" / "claudechat_hook.py"
    register(SETTINGS_PATH, hook)
    return str(hook)


def remove_service() -> bool:
    if not UNIT_PATH.exists():
        return False
    subprocess.run(["systemctl", "--user", "disable", "--now", "claudechat"],
                   capture_output=True, text=True)
    UNIT_PATH.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
    return True


def command_install(with_service: bool = False) -> int:
    project_root = Path(__file__).resolve().parents[3]

    hook = install_hook(project_root)
    print(f"registered Stop hook   {hook}")
    print(f"                    in {SETTINGS_PATH}")

    if with_service:
        unit = install_service(project_root)
        print(f"wrote service unit     {unit}")
        for args in (
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "claudechat"],
        ):
            result = subprocess.run(args, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  {' '.join(args)} failed: {result.stderr.strip()[:120]}", file=sys.stderr)
                break
        else:
            print("service enabled — the daemon now starts with your session")
    else:
        print("no autostart installed — start the daemon per session with ./start.sh")
        print("                        or add autostart later with ./start.sh --autostart")

    print()
    print("Speech is OFF by default. Turn it on with:  claudechat on")
    print("Check anything with:                        claudechat status")
    print("Remove everything with:                     ./start.sh --uninstall")
    return 0
