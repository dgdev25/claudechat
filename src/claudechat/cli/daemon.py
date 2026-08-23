"""Always-on mode: a resident daemon plus an instant on/off toggle.

The daemon holds the speech models in memory and owns the socket the Claude Code
Stop hook posts to, so speaking a reply costs no model-loading time. The toggle
edits one value in the config file; the daemon re-reads it per announcement, so
switching takes effect on the very next reply with no restart.
"""

from __future__ import annotations

import signal
import sys
import threading
import tomllib
from pathlib import Path

from claudechat.config import DEFAULT_CONFIG_PATH, Config, load_config


def _set_spoken_summaries(enabled: bool, path: Path | None = None) -> Path:
    """Write `spoken_summaries` into the config file, preserving everything else."""
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        lines = path.read_text().splitlines()
    else:
        lines = ["[hook]"]

    value = "true" if enabled else "false"
    in_hook = False
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_hook and not replaced:
                out.append(f"spoken_summaries = {value}")
                replaced = True
            in_hook = stripped == "[hook]"
        elif in_hook and stripped.startswith("spoken_summaries"):
            out.append(f"spoken_summaries = {value}")
            replaced = True
            continue
        out.append(line)

    if not replaced:
        if "[hook]" not in [line.strip() for line in out]:
            out.append("[hook]")
        out.append(f"spoken_summaries = {value}")

    path.write_text("\n".join(out) + "\n")
    return path


def _is_enabled(path: Path | None = None) -> bool:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config.spoken_summaries
    with path.open("rb") as handle:
        return bool(tomllib.load(handle).get("hook", {}).get("spoken_summaries", False))


def _daemon_running(config: Config) -> bool:
    return (config.runtime_dir / "engine.sock").is_socket()


def _autostart_installed() -> bool:
    return (Path.home() / ".config" / "systemd" / "user" / "claudechat.service").exists()


def _how_to_start() -> str:
    if _autostart_installed():
        return "start it with:  systemctl --user start claudechat"
    return "start it with:  ./start.sh        (this session only)"


def command_toggle(argument: str) -> int:
    """on / off / toggle / status."""
    if argument == "status":
        config = load_config()
        speaking = "on" if _is_enabled() else "off"
        running = "running" if _daemon_running(config) else "NOT running"
        print(f"speech: {speaking}    daemon: {running}    voice: {config.tts_voice}")
        autostart = "on" if _autostart_installed() else "off"
        print(f"autostart: {autostart}")
        if not _daemon_running(config):
            print(_how_to_start())
        return 0

    if argument == "toggle":
        enabled = not _is_enabled()
    else:
        enabled = argument == "on"

    _set_spoken_summaries(enabled)
    config = load_config()
    print(f"speech {'on' if enabled else 'off'}")
    if enabled and not _daemon_running(config):
        print(f"daemon is not running — {_how_to_start()}")
    return 0


def command_serve() -> int:
    """Run the engine until stopped. Models stay resident between replies."""
    from claudechat.cli.terminal import Engine

    engine = Engine(load_config(), config_provider=load_config)
    engine.start()
    engine.preload()

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
    if command in {"on", "off", "toggle", "status"}:
        return command_toggle(command)
    if command in {"install", "autostart"}:
        from claudechat.cli.install import command_install

        return command_install(with_service=command == "autostart")

    if command == "uninstall-service":
        from claudechat.cli.install import remove_service

        print("autostart removed" if remove_service() else "no autostart was installed")
        return 0

    print(
        "usage: claudechat [serve|on|off|toggle|status|install|autostart]\n"
        "  (no argument)  interactive voice session\n"
        "  serve          run the daemon in the foreground\n"
        "  on|off|toggle  speak Claude Code replies, or stop speaking them\n"
        "  status         show whether speech and the daemon are on\n"
        "  install        register the Stop hook only (no autostart)\n"
        "  autostart      also install and enable the systemd user service",
        file=sys.stderr,
    )
    return 2
