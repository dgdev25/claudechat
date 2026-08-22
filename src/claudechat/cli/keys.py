from __future__ import annotations

import sys
import termios
import tty
from collections.abc import Iterator

# Read from this machine's GNOME settings: initial delay 500 ms, repeat
# interval 30 ms. A single gap value cannot serve both — see HoldDetector.
DEFAULT_INITIAL_DELAY_SECONDS = 0.5
DEFAULT_REPEAT_INTERVAL_SECONDS = 0.03


class HoldDetector:
    """Infer 'key is held' from terminal auto-repeat.

    Terminals report presses, not releases, so holding is inferred from the
    repeat stream. That stream has two phases with very different timing: the
    first repeat arrives only after the initial delay (500 ms on this machine),
    then the rest follow at the repeat interval (30 ms).

    A single release gap cannot serve both. A gap short enough to detect release
    promptly — 250 ms, as first written — reports the key released between
    250 ms and 500 ms while it is still physically held, so recording cuts out
    on every press. A gap long enough to span the initial delay leaves release
    detection sluggish for the entire hold.

    So the tolerated gap is initial-delay-sized until the first repeat arrives,
    then interval-sized for the rest of the hold.
    """

    def __init__(
        self,
        release_gap_seconds: float | None = None,
        initial_delay_seconds: float = DEFAULT_INITIAL_DELAY_SECONDS,
        repeat_interval_seconds: float = DEFAULT_REPEAT_INTERVAL_SECONDS,
    ) -> None:
        # Allow a quarter again over the configured delay for scheduling jitter.
        self._initial_window = initial_delay_seconds * 1.25
        self._repeat_window = (
            release_gap_seconds
            if release_gap_seconds is not None
            else max(repeat_interval_seconds * 4.0, 0.12)
        )
        self._last: float | None = None
        self._repeats = 0

    def press(self, now: float) -> None:
        if self._last is not None:
            self._repeats += 1
        self._last = now

    def is_held(self, now: float) -> bool:
        if self._last is None:
            return False
        window = self._repeat_window if self._repeats else self._initial_window
        return (now - self._last) <= window

    def release(self) -> None:
        """Forget the current hold so the next press starts a fresh one."""
        self._last = None
        self._repeats = 0


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
