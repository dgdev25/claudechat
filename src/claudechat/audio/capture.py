from __future__ import annotations

import os
import signal
import subprocess
import threading

from claudechat.audio.backend import capture_command
from claudechat.config import Config


class Capture:
    """Record 16 kHz mono 16-bit PCM from PipeWire, with a hard time limit."""

    sample_rate = 16000

    def __init__(self, config: Config) -> None:
        self._max_seconds = config.max_recording_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._chunks: list[bytes] = []
        self._taken: list[bytes] = []
        self._reader: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._argv = capture_command(self.sample_rate)

    def start(self) -> None:
        with self._lock:
            if self._process is not None:
                return
            self._chunks = []
            self._taken = []
            self._process = subprocess.Popen(
                self._argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
            process = self._process

        def read() -> None:
            try:
                while True:
                    block = process.stdout.read(4096) if process.stdout else b""
                    if not block:
                        break
                    with self._lock:
                        self._chunks.append(block)
            except (ValueError, OSError):
                pass

        self._reader = threading.Thread(target=read, daemon=True)
        self._reader.start()
        self._timer = threading.Timer(self._max_seconds, self._halt)
        self._timer.daemon = True
        self._timer.start()

    def is_recording(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def take(self) -> bytes:
        """Atomically return accumulated audio blocks and clear them.

        Returns the concatenated audio since start() or the last take() call.
        """
        with self._lock:
            result = b"".join(self._chunks)
            self._taken.extend(self._chunks)
            self._chunks = []
        return result

    def stop(self) -> bytes:
        self._halt()
        if self._reader is not None:
            self._reader.join(timeout=1.0)
            self._reader = None
        with self._lock:
            return b"".join(self._taken + self._chunks)

    def _halt(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        with self._lock:
            process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=0.5)
        except (ProcessLookupError, PermissionError):
            pass
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
