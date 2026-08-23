from __future__ import annotations

from claudechat.audio.backend import playback_command

import os
import signal
import subprocess
import threading
import time
from collections import deque


class Playback:
    """Play 16-bit little-endian mono PCM through PipeWire, gapless.

    One long-lived player process; chunks queue and a single feeder thread
    writes them back-to-back, so a new chunk never truncates the one still
    playing. cancel() drops the queue and kills the process, which also breaks
    any in-flight pipe write — the feeder must never block while holding the
    lock, or cancel() would wait on the pipe draining.
    """

    def __init__(self, sample_rate: int, target: str = "") -> None:
        self._sample_rate = sample_rate
        self._process: subprocess.Popen[bytes] | None = None
        self._chunks: deque[tuple[int, bytes]] = deque()
        self._cond = threading.Condition()
        self._generation = 0
        self._inflight: int | None = None  # generation of the chunk being written
        self._drain_deadline = 0.0
        self._feeder: threading.Thread | None = None
        # Resolved per platform; raises AudioUnavailable with install
        # instructions rather than failing obscurely at spawn time.
        self._argv = playback_command(sample_rate, target=target)

    def play(self, pcm: bytes) -> None:
        """Queue PCM and return immediately. Chunks play in order, gapless."""
        if not pcm:
            return
        with self._cond:
            now = time.monotonic()
            self._drain_deadline = (
                max(self._drain_deadline, now) + len(pcm) / (2 * self._sample_rate)
            )
            self._chunks.append((self._generation, pcm))
            if self._feeder is None or not self._feeder.is_alive():
                self._feeder = threading.Thread(target=self._feed, daemon=True)
                self._feeder.start()
            self._cond.notify()

    def is_playing(self) -> bool:
        """True while queued, in-flight, or already-written audio remains."""
        with self._cond:
            # An in-flight chunk of a cancelled generation is already dying in
            # a broken pipe write; it no longer counts as playing.
            if self._chunks or self._inflight == self._generation:
                return True
            alive = self._process is not None and self._process.poll() is None
            return alive and time.monotonic() < self._drain_deadline

    def wait(self, timeout: float | None = None) -> None:
        """Block until every queued chunk has drained, or the timeout expires."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_playing():
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(0.02)

    def cancel(self) -> None:
        """Stop audio now and drop everything queued."""
        with self._cond:
            self._generation += 1
            self._chunks.clear()
            self._drain_deadline = 0.0
            self._stop_locked()
            self._cond.notify()

    def _feed(self) -> None:
        while True:
            with self._cond:
                while not self._chunks:
                    if not self._cond.wait(timeout=5.0) and not self._chunks:
                        self._feeder = None
                        return
                generation, pcm = self._chunks.popleft()
                if generation != self._generation:
                    continue
                self._inflight = generation
                process = self._ensure_process_locked()
            # Blocking write, outside the lock: it stalls whenever the pipe
            # buffer is full. cancel() kills the process, which breaks the
            # write; a chunk cancelled between the pop and the write dies the
            # same way.
            try:
                if process is not None and process.stdin is not None:
                    process.stdin.write(pcm)
                    process.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                with self._cond:
                    if self._process is process:
                        self._process = None
            finally:
                with self._cond:
                    self._inflight = None

    def _ensure_process_locked(self) -> subprocess.Popen[bytes] | None:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = None
        try:
            self._process = subprocess.Popen(
                self._argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                shell=False,
            )
        except OSError:
            return None
        return self._process

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
