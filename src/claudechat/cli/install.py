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

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / "claudechat.service"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.claudechat.daemon.plist"
LAUNCHD_LABEL = "com.claudechat.daemon"


def is_macos() -> bool:
    return sys.platform == "darwin"


def service_path() -> Path:
    return PLIST_PATH if is_macos() else UNIT_PATH

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
    """Write the autostart definition for whichever service manager this OS has."""
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv not found on PATH; cannot write a service definition")

    if is_macos():
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        logs = project_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_bytes(plistlib.dumps({
            "Label": LAUNCHD_LABEL,
            "ProgramArguments": [uv, "run", "--project", str(project_root),
                                 "claudechat", "serve"],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "WorkingDirectory": str(project_root),
            "StandardOutPath": str(logs / "daemon.log"),
            "StandardErrorPath": str(logs / "daemon.log"),
            "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        }))
        return PLIST_PATH

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
    path = service_path()
    if not path.exists():
        return False
    if is_macos():
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True, text=True)
        path.unlink()
        return True
    subprocess.run(["systemctl", "--user", "disable", "--now", "claudechat"],
                   capture_output=True, text=True)
    path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
    return True


def _enable_commands(path: Path) -> list[list[str]]:
    if is_macos():
        return [["launchctl", "unload", str(path)], ["launchctl", "load", "-w", str(path)]]
    return [["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "claudechat"]]


def install_launcher(project_root: Path) -> Path | None:
    """Put `claudechat` on PATH.

    Without this the commands only work as `uv run claudechat` from inside the
    repo, which defeats a toggle you are supposed to reach from anywhere.
    """
    target = project_root / ".venv" / "bin" / "claudechat"
    if not target.exists():
        return None
    bindir = Path.home() / ".local" / "bin"
    if not bindir.is_dir():
        return None
    link = bindir / "claudechat"
    if link.is_symlink() or link.exists():
        if link.is_symlink() and link.resolve() == target.resolve():
            return link
        link.unlink()
    link.symlink_to(target)
    return link


def command_install(with_service: bool = False) -> int:
    project_root = Path(__file__).resolve().parents[3]

    launcher = install_launcher(project_root)
    if launcher:
        print(f"linked launcher       {launcher}")
    else:
        print("could not put claudechat on PATH — use 'uv run claudechat' from the repo")

    hook = install_hook(project_root)
    print(f"registered Stop hook   {hook}")
    print(f"                    in {SETTINGS_PATH}")

    if with_service:
        unit = install_service(project_root)
        manager = "launchd" if is_macos() else "systemd"
        print(f"wrote {manager} definition  {unit}")
        for args in _enable_commands(unit):
            result = subprocess.run(args, capture_output=True, text=True)
            # launchctl unload of a not-yet-loaded job returns non-zero; that is
            # expected on a first install, so only the final command must pass.
            if result.returncode != 0 and args is _enable_commands(unit)[-1]:
                print(f"  {' '.join(args)} failed: {result.stderr.strip()[:120]}", file=sys.stderr)
                break
        else:
            print(f"service enabled via {manager} — the daemon now starts with your session")
    else:
        print("no autostart installed — start the daemon per session with ./start.sh")
        print("                        or add autostart later with ./start.sh --autostart")

    print()
    print("Speech is OFF by default. Turn it on with:  claudechat on")
    print("Check anything with:                        claudechat status")
    print("Remove everything with:                     ./start.sh --uninstall")
    return 0
