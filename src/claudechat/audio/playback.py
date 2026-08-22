from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading


class Playback:
    """Play 16-bit little-endian mono PCM through PipeWire."""

    def __init__(self, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._binary = shutil.which("pw-play")
        if self._binary is None:
            raise RuntimeError("pw-play not found; install pipewire-utils")

    def play(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self._lock:
            self._stop_locked()
            self._process = subprocess.Popen(
                [
                    self._binary,
                    "--format=s16",
                    f"--rate={self._sample_rate}",
                    "--channels=1",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
            process = self._process

        def feed() -> None:
            try:
                if process.stdin:
                    process.stdin.write(pcm)
                    process.stdin.close()
                process.wait()
            except (BrokenPipeError, ValueError, OSError):
                pass

        threading.Thread(target=feed, daemon=True).start()

    def is_playing(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def cancel(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
