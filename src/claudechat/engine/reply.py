from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Callable

from claudechat.audio.capture import Capture
from claudechat.audio.vad import SpeechGate
from claudechat.config import Config
from claudechat.speech.transcriber import WhisperTranscriber
from claudechat.text.strip import strip_control_characters

_log = logging.getLogger("claudechat.reply")


class VoiceReplyListener:
    """After a spoken summary, listen briefly and copy the reply to the clipboard."""

    def __init__(
        self,
        config: Config,
        capture_factory: Callable[[], Capture],
        transcriber_factory: Callable[[], WhisperTranscriber],
        gate_factory: Callable[[], SpeechGate],
        speak: Callable[[str], None],
        copy_to_clipboard: Callable[[str], None] | None = None,
    ) -> None:
        self._config = config
        self._capture_factory = capture_factory
        self._transcriber_factory = transcriber_factory
        self._gate_factory = gate_factory
        self._speak = speak
        self._copy_to_clipboard = copy_to_clipboard or self._default_copy_to_clipboard
        self._capture: Capture | None = None
        self._transcriber: WhisperTranscriber | None = None

    @staticmethod
    def _default_copy_to_clipboard(text: str) -> None:
        """Try system clipboard tools in order: wl-copy, xclip, pbcopy."""
        for cmd in ["wl-copy", "xclip", "pbcopy"]:
            if cmd == "xclip":
                full_cmd = [cmd, "-selection", "clipboard"]
            else:
                full_cmd = [cmd]
            if shutil.which(full_cmd[0]):
                try:
                    subprocess.run(
                        full_cmd,
                        input=text.encode(),
                        timeout=5,
                        check=True,
                    )
                    return
                except (subprocess.CalledProcessError, OSError):
                    continue
        raise RuntimeError("No clipboard tool found (wl-copy, xclip, or pbcopy)")

    def listen_once(self) -> str:
        """Listen for voice reply; copy to clipboard and return text.

        Returns empty string if no speech detected, window expires, or any error.
        """
        try:
            # Lazy-load capture and transcriber on first use
            if self._capture is None:
                self._capture = self._capture_factory()
            if self._transcriber is None:
                self._transcriber = self._transcriber_factory()

            gate = self._gate_factory()
            self._capture.start()

            start_time = time.monotonic()
            while time.monotonic() - start_time < self._config.voice_reply_window_seconds:
                pcm = self._capture.take()
                if pcm and gate.feed(pcm) == "end":
                    break
                time.sleep(0.05)

            full_pcm = self._capture.stop()

            # No speech detected
            if gate.state == "waiting":
                return ""

            # Transcribe
            text = strip_control_characters(
                self._transcriber.transcribe(full_pcm, self._capture.sample_rate)
            ).strip()

            if not text:
                return ""

            # Copy to clipboard
            try:
                self._copy_to_clipboard(text)
            except RuntimeError:
                _log.exception("clipboard tool not found")
                return ""

            # Confirm
            self._speak("Copied. Paste it into Claude Code.")
            return text

        except Exception:
            _log.exception("voice reply listener error")
            return ""
