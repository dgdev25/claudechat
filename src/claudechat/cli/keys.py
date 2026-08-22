from __future__ import annotations

import sys
import termios
import tty
from collections.abc import Iterator


class HoldDetector:
    """Infer 'key is held' from terminal auto-repeat.

    Terminals report presses, not releases. A held key repeats at the system
    repeat rate, so a gap longer than release_gap_seconds means released.
    """

    def __init__(self, release_gap_seconds: float = 0.25) -> None:
        self._gap = release_gap_seconds
        self._last: float | None = None

    def press(self, now: float) -> None:
        self._last = now

    def is_held(self, now: float) -> bool:
        if self._last is None:
            return False
        return (now - self._last) <= self._gap


def read_key_events(stream=None) -> Iterator[str]:
    """Yield single characters from a terminal in raw mode."""
    stream = stream or sys.stdin
    fd = stream.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            char = stream.read(1)
            if not char:
                return
            yield char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
