"""Per-platform audio commands, behind one interface.

Audio is the only genuinely platform-specific part of claudechat. Everything
else — the models, the text handling, the Claude backend, the hook — is
portable. So the split lives here rather than being scattered through the
capture and playback classes.

The design stays subprocess-based rather than adopting a cross-platform audio
library. PortAudio bindings ship no Linux wheels, so adding one would trade a
setup that currently needs no native dependencies on Linux for one that does.

Every command reads or writes RAW 16-bit little-endian mono PCM on a pipe, so
the callers are identical on both platforms.

Linux  — PipeWire's pw-cat. Present wherever PipeWire is.
macOS  — sox, else ffmpeg. Neither ships with macOS; the error names the
         Homebrew command rather than failing obscurely. `afplay` is not usable
         here: it plays files, not a raw stream on stdin.
"""

from __future__ import annotations

import platform
import shutil


class AudioUnavailable(RuntimeError):
    """No usable audio tool for this platform, with instructions to fix it."""


def _macos_hint(what: str) -> str:
    return (
        f"No usable {what} tool found on macOS.\n"
        "  Install one of:\n"
        "    brew install sox        (recommended, smaller)\n"
        "    brew install ffmpeg\n"
        "  macOS ships no command-line tool that streams raw PCM."
    )


def _linux_hint(what: str) -> str:
    return (
        f"No usable {what} tool found.\n"
        "  claudechat uses PipeWire. Install it with:\n"
        "    sudo apt install pipewire-bin        (Debian/Ubuntu)\n"
        "    sudo dnf install pipewire-utils      (Fedora)"
    )


def is_macos() -> bool:
    return platform.system() == "Darwin"


def playback_command(sample_rate: int, target: str = "") -> list[str]:
    """Command that plays raw s16le mono PCM arriving on stdin.

    On Linux with PipeWire, target specifies the sink node name (e.g.
    "claudechat_ec_sink"). On macOS, target is ignored (no equivalent).
    """
    if is_macos():
        sox = shutil.which("play")
        if sox:
            # -q quiet, -t raw with explicit encoding, "-" reads stdin.
            return [sox, "-q", "-t", "raw", "-r", str(sample_rate),
                    "-e", "signed", "-b", "16", "-c", "1", "-"]
        ffmpeg = shutil.which("ffplay")
        if ffmpeg:
            return [ffmpeg, "-loglevel", "quiet", "-nodisp", "-autoexit",
                    "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-"]
        raise AudioUnavailable(_macos_hint("playback"))

    pw_cat = shutil.which("pw-cat")
    if pw_cat:
        cmd = [pw_cat, "--playback", "--raw", "--format=s16",
                f"--rate={sample_rate}", "--channels=1", "-"]
        if target:
            cmd.extend(["--target", target])
        return cmd
    raise AudioUnavailable(_linux_hint("playback"))


def capture_command(sample_rate: int, target: str = "") -> list[str]:
    """Command that writes raw s16le mono PCM from the microphone to stdout.

    On Linux with PipeWire, target specifies the source node name (e.g.
    "claudechat_ec_source"). On macOS, target is ignored (no equivalent).
    """
    if is_macos():
        rec = shutil.which("rec")
        if rec:
            # -d is the default input device.
            return [rec, "-q", "-t", "raw", "-r", str(sample_rate),
                    "-e", "signed", "-b", "16", "-c", "1", "-", "-d"]
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return [ffmpeg, "-loglevel", "quiet", "-f", "avfoundation",
                    "-i", ":default", "-f", "s16le", "-ar", str(sample_rate),
                    "-ac", "1", "-"]
        raise AudioUnavailable(_macos_hint("recording"))

    pw_record = shutil.which("pw-record")
    if pw_record:
        cmd = [pw_record, "--format=s16", f"--rate={sample_rate}",
                "--channels=1", "-"]
        if target:
            cmd.extend(["--target", target])
        return cmd
    raise AudioUnavailable(_linux_hint("recording"))
