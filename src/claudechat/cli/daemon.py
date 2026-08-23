"""Always-on mode: a resident daemon plus an instant on/off toggle.

The daemon holds the speech models in memory and owns the socket the Claude Code
Stop hook posts to, so speaking a reply costs no model-loading time. The toggle
edits one value in the config file; the daemon re-reads it per announcement, so
switching takes effect on the very next reply with no restart.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

from claudechat.config import DEFAULT_CONFIG_PATH, Config, load_config


def _set_hook_key(key: str, value: str, path: Path | None = None) -> Path:
    """Write a key into the [hook] section, preserving everything else.

    Args:
        key: The TOML key to set (e.g., "spoken_summaries", "focus_cwd")
        value: The TOML value as a string. For bool, use "true" or "false".
               For string, pass the quoted value (caller must quote).
        path: Config file path; defaults to DEFAULT_CONFIG_PATH
    """
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        lines = path.read_text().splitlines()
    else:
        lines = ["[hook]"]

    in_hook = False
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_hook and not replaced:
                out.append(f"{key} = {value}")
                replaced = True
            in_hook = stripped == "[hook]"
        elif in_hook and stripped.startswith(key):
            out.append(f"{key} = {value}")
            replaced = True
            continue
        out.append(line)

    if not replaced:
        if "[hook]" not in [line.strip() for line in out]:
            out.append("[hook]")
        out.append(f"{key} = {value}")

    path.write_text("\n".join(out) + "\n")
    return path


def _set_spoken_summaries(enabled: bool, path: Path | None = None) -> Path:
    """Write `spoken_summaries` into the config file, preserving everything else."""
    value = "true" if enabled else "false"
    return _set_hook_key("spoken_summaries", value, path)


def _is_enabled(path: Path | None = None) -> bool:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config.spoken_summaries
    with path.open("rb") as handle:
        return bool(tomllib.load(handle).get("hook", {}).get("spoken_summaries", False))


def _daemon_running(config: Config) -> bool:
    """True only if something answers the socket — a daemon that died without
    cleanup leaves the socket file behind, and stat alone reports it running."""
    path = config.runtime_dir / "engine.sock"
    if not path.is_socket():
        return False
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        probe.connect(str(path))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _autostart_installed() -> bool:
    from claudechat.cli.install import service_path

    return service_path().exists()


def _how_to_start() -> str:
    if _autostart_installed():
        if sys.platform == "darwin":
            return "start it with:  launchctl start com.claudechat.daemon"
        return "start it with:  systemctl --user start claudechat"
    return "start it with:  claudechat on     (starts the engine itself)"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def start_daemon(timeout_seconds: float = 120.0) -> bool:
    """Launch the daemon in the background and wait until it accepts a connection.

    setsid --fork is load-bearing: plain setsid does not fork when it is already
    a process-group leader, and the daemon would stay a child of this short-lived
    command, dying with it.
    """
    config = load_config()
    if _daemon_running(config):
        return True

    root = _project_root()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "daemon.log").open("a")
    uv = shutil.which("uv")
    argv = (
        [uv, "run", "--project", str(root), "claudechat", "serve"]
        if uv
        else [sys.executable, "-m", "claudechat.cli.daemon", "serve"]
    )

    # Detach so the daemon outlives this short-lived command. `setsid --fork` is
    # util-linux and does not exist on macOS, and plain `setsid` does not fork
    # when it is already a process-group leader — so do it in Python, which
    # behaves the same everywhere. start_new_session=True calls setsid(2) in the
    # child after fork, which is exactly what is wanted.
    with open(os.devnull) as devnull:
        subprocess.Popen(
            argv,
            cwd=root,
            stdin=devnull,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )

    deadline = time.monotonic() + timeout_seconds
    socket_path = config.runtime_dir / "engine.sock"
    poll_delay = 0.05
    while time.monotonic() < deadline:
        if socket_path.is_socket():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(1.0)
            try:
                probe.connect(str(socket_path))
                return True
            except OSError:
                pass
            finally:
                probe.close()
        time.sleep(poll_delay)
        poll_delay = min(poll_delay * 1.5, 0.5)
    return False


def stop_daemon() -> bool:
    """Stop a running daemon. Returns True if one was stopped."""
    config = load_config()
    if not _daemon_running(config):
        return False
    result = subprocess.run(
        ["pkill", "-f", "claudechat.cli.daemon serve|claudechat serve"],
        capture_output=True,
    )
    for _ in range(20):
        if not _daemon_running(config):
            break
        time.sleep(0.2)
    (config.runtime_dir / "engine.sock").unlink(missing_ok=True)
    return result.returncode in (0, 1)


def command_toggle(argument: str) -> int:
    """on / off / toggle / status."""
    if argument == "status":
        config = load_config()
        speaking = "on" if _is_enabled() else "off"
        running = "running" if _daemon_running(config) else "NOT running"
        print(f"speech: {speaking}    daemon: {running}    voice: {config.tts_voice}")
        autostart = "on" if _autostart_installed() else "off"
        print(f"autostart: {autostart}")
        barge_in = "on" if config.voice_barge_in else "off"
        print(f"voice barge-in: {barge_in}")
        if config.focus_cwd:
            print(f"focus: {config.focus_cwd}")
        if not _daemon_running(config):
            print(_how_to_start())
        return 0

    if argument == "toggle":
        enabled = not _is_enabled()
    else:
        enabled = argument == "on"

    _set_spoken_summaries(enabled)

    # The toggle is the whole interaction: turning speech on starts the engine
    # if it is not already up, and turning it off shuts it down again, so a
    # user never has to run a separate launcher. When autostart is installed the
    # daemon is managed by systemd and is left alone.
    if _autostart_installed():
        print(f"speech {'on' if enabled else 'off'}")
        return 0

    if enabled:
        if _daemon_running(load_config()):
            print("speech on")
            return 0
        print("speech on — starting the engine...", flush=True)
        print("  (first ever run downloads speech models, a few minutes)", flush=True)
        if start_daemon():
            print("ready")
            return 0
        print("engine failed to start — see logs/daemon.log", file=sys.stderr)
        return 1

    stopped = stop_daemon()
    print("speech off" + (" — engine stopped" if stopped else ""))
    return 0


def command_focus(argument: str | None = None, path: Path | None = None) -> int:
    """Set focus to current directory, or clear it with 'off'."""
    if argument == "off":
        _set_hook_key("focus_cwd", '""', path)
        print("focus off — all sessions are spoken")
        return 0

    cwd = os.getcwd()
    focus_value = json.dumps(cwd)  # Properly quote the path for TOML
    _set_hook_key("focus_cwd", focus_value, path)
    print(f"focus: {cwd} (only this project is spoken)")
    return 0


def command_serve() -> int:
    """Run the engine until stopped. Models stay resident between replies."""
    import logging

    from claudechat.cli.terminal import Engine

    # Every announcement outcome is logged. Without this, a reply that is not
    # spoken is indistinguishable from a broken engine.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        datefmt="%H:%M:%S")

    engine = Engine(load_config(), config_provider=load_config)
    # Load the models BEFORE binding the socket. The socket appearing is what
    # everything else treats as "ready"; binding first would advertise a daemon
    # that cannot speak yet, and `claudechat on` would report ready in half a
    # second while the first reply still waited 30s for Kokoro.
    engine.preload()
    engine.start()

    stopping = threading.Event()

    def shutdown(_signum, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    config = load_config()
    print(
        f"claudechat daemon ready — voice {config.tts_voice}, "
        f"speech {'on' if _is_enabled() else 'off'}, "
        f"socket {engine.service.socket_path}",
        flush=True,
    )
    try:
        stopping.wait()
    finally:
        engine.stop()
        print("claudechat daemon stopped", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        from claudechat.cli.terminal import interactive_main

        return interactive_main()

    command = argv[0]
    if command == "serve":
        return command_serve()
    if command == "daemon-start":
        # Start the engine without touching the speech setting. start.sh uses
        # this so both paths share one portable detachment implementation.
        if start_daemon():
            print("engine ready")
            return 0
        print("engine failed to start — see logs/daemon.log", file=sys.stderr)
        return 1
    if command == "daemon-stop":
        print("engine stopped" if stop_daemon() else "engine was not running")
        return 0
    if command in {"on", "off", "toggle", "status"}:
        return command_toggle(command)
    if command == "focus":
        argument = argv[1] if len(argv) > 1 else None
        return command_focus(argument)
    if command in {"install", "autostart"}:
        from claudechat.cli.install import command_install

        return command_install(with_service=command == "autostart")

    if command == "uninstall-service":
        from claudechat.cli.install import remove_service

        print("autostart removed" if remove_service() else "no autostart was installed")
        return 0

    if command == "setup-echo-cancel":
        from claudechat.cli.echocancel import command_setup

        return command_setup()

    print(
        "usage: claudechat [serve|on|off|toggle|status|focus|install|autostart|setup-echo-cancel]\n"
        "  (no argument)  interactive voice session\n"
        "  serve          run the daemon in the foreground\n"
        "  on|off|toggle  speak Claude Code replies, or stop speaking them\n"
        "  status         show whether speech and the daemon are on\n"
        "  focus          set to speak only this project directory\n"
        "  focus off      speak all sessions (clear focus)\n"
        "  daemon-start   start the engine without changing the speech setting\n"
        "  daemon-stop    stop the engine\n"
        "  install        register the Stop hook only (no autostart)\n"
        "  autostart      also install and enable the systemd user service\n"
        "  setup-echo-cancel  set up PipeWire echo cancellation for voice barge-in",
        file=sys.stderr,
    )
    return 2
