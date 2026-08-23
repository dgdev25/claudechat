"""Setup PipeWire echo cancellation for voice barge-in.

The echo-cancelled microphone path stops the voice barge-in detector from
triggering on the assistant's speech that the user hears from the speakers. The
setup writes a PipeWire module config and updates the claudechat config.
"""

from __future__ import annotations

import glob
import subprocess
import sys
import time
from pathlib import Path

from claudechat.audio.backend import is_macos
from claudechat.config import DEFAULT_CONFIG_PATH

PIPEWIRE_CONF = """# claudechat: echo-cancelled microphone path, so voice barge-in does not
# trigger on the assistant's own speech coming from the speakers.
# Playback routed into claudechat_ec_sink is used as the cancellation
# reference; claudechat_ec_source is the microphone with that audio removed.
# Noise suppression and gain control are disabled: they crush the user's
# voice during double-talk, which is exactly when barge-in must hear it.
context.modules = [
    { name = libpipewire-module-echo-cancel
        args = {
            aec.args = {
                webrtc.noise_suppression = false
                webrtc.gain_control = false
                webrtc.high_pass_filter = true
            }
            capture.props = {
                node.name = "claudechat_ec_capture"
                node.description = "claudechat mic (raw)"
            }
            source.props = {
                node.name = "claudechat_ec_source"
                node.description = "claudechat mic (echo-cancelled)"
            }
            sink.props = {
                node.name = "claudechat_ec_sink"
                node.description = "claudechat speech output (echo reference)"
            }
            playback.props = {
                node.name = "claudechat_ec_playback"
            }
        }
    }
]
"""


def conf_path() -> Path:
    """Return the PipeWire echo-cancel config file path."""
    return Path.home() / ".config" / "pipewire" / "pipewire.conf.d" / "99-claudechat-echo-cancel.conf"


def _set_key(section: str, key: str, value: str, path: Path | None = None) -> Path:
    """Write a key into a TOML section, preserving everything else.

    Args:
        section: The TOML section name (e.g., "hook", "speech")
        key: The TOML key to set (e.g., "spoken_summaries", "voice_barge_in")
        value: The TOML value as a string. For bool, use "true" or "false".
               For string, pass the quoted value (caller must quote).
        path: Config file path; defaults to DEFAULT_CONFIG_PATH
    """
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        lines = path.read_text().splitlines()
    else:
        lines = [f"[{section}]"]

    in_section = False
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:
                out.append(f"{key} = {value}")
                replaced = True
            in_section = stripped == f"[{section}]"
        elif in_section and stripped.startswith(key):
            out.append(f"{key} = {value}")
            replaced = True
            continue
        out.append(line)

    if not replaced:
        if f"[{section}]" not in [line.strip() for line in out]:
            out.append(f"[{section}]")
        out.append(f"{key} = {value}")

    path.write_text("\n".join(out) + "\n")
    return path


def command_setup(restart: bool = True) -> int:
    """Set up echo cancellation for voice barge-in.

    Returns 0 on success, 1 on failure.
    """
    # Check if this is macOS (not supported)
    if is_macos():
        print("echo-cancel setup is Linux/PipeWire-only. voice barge-in stays off on macOS.", file=sys.stderr)
        return 1

    # Check for the echo-cancel module file
    module_patterns = [
        "/usr/lib/*/pipewire-*/libpipewire-module-echo-cancel.so",
        "/usr/lib64/*/pipewire-*/libpipewire-module-echo-cancel.so",
    ]
    module_found = False
    for pattern in module_patterns:
        if glob.glob(pattern):
            module_found = True
            break

    if not module_found:
        print(
            "echo-cancel module not found. Install PipeWire fully with:\n"
            "  sudo apt install pipewire        (Debian/Ubuntu)\n"
            "  sudo dnf install pipewire-utils  (Fedora)",
            file=sys.stderr,
        )
        return 1

    # Write the PipeWire config
    conf = conf_path()
    conf.parent.mkdir(parents=True, exist_ok=True)
    if conf.exists() and conf.read_text() == PIPEWIRE_CONF:
        pass  # Already has the same content, skip write
    else:
        conf.write_text(PIPEWIRE_CONF)

    # Restart PipeWire if requested
    if restart:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "pipewire", "wireplumber"],
            capture_output=True,
        )
        if result.returncode != 0:
            print(
                "failed to restart PipeWire. A re-login also applies the config.",
                file=sys.stderr,
            )
            return 1

        # Poll for the echo-cancel nodes to appear
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                output = subprocess.check_output(
                    ["pw-cli", "ls", "Node"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
                if "claudechat_ec_source" in output and "claudechat_ec_sink" in output:
                    break
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            time.sleep(0.1)
        else:
            print(
                "warning: echo-cancel nodes did not appear after restart. "
                "Check PipeWire status with 'pw-cli ls Node'.",
                file=sys.stderr,
            )
            return 1

    # Migrate old setups: if capture_target is set to the echo-cancelled source,
    # move it to barge_capture_target and clear capture_target (main recording
    # uses raw microphone for better transcription).
    cfg_path = DEFAULT_CONFIG_PATH
    if cfg_path.exists():
        lines = cfg_path.read_text().splitlines()
        migrated = False
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("capture_target") and "claudechat_ec_source" in stripped:
                out.append('capture_target = ""')
                migrated = True
            else:
                out.append(line)
        if migrated:
            cfg_path.write_text("\n".join(out) + "\n")

    # Write config keys to the [speech] section
    _set_key("speech", "barge_capture_target", '"claudechat_ec_source"')
    _set_key("speech", "playback_target", '"claudechat_ec_sink"')
    _set_key("speech", "voice_barge_in", "true")

    print("voice barge-in enabled. Disable with: voice_barge_in = false in config")
    return 0
