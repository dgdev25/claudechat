from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading

from claudechat.config import Config


class Capture:
    """Record 16 kHz mono 16-bit PCM from PipeWire, with a hard time limit."""

    sample_rate = 16000

    def __init__(self, config: Config) -> None:
        self._max_seconds = config.max_recording_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._chunks: list[bytes] = []
        self._reader: threading.Thread | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._binary = shutil.which("pw-record")
        if self._binary is None:
            raise RuntimeError("pw-record not found; install pipewire-utils")

    def start(self) -> None:
        with self._lock:
            if self._process is not None:
                return
            self._chunks = []
            self._process = subprocess.Popen(
                [
                    self._binary,
                    "--format=s16",
                    f"--rate={self.sample_rate}",
                    "--channels=1",
                    "-",
                ],
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

    def stop(self) -> bytes:
        self._halt()
        if self._reader is not None:
            self._reader.join(timeout=1.0)
            self._reader = None
        return b"".join(self._chunks)

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
