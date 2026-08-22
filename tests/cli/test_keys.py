from claudechat.cli.keys import HoldDetector


def test_held_while_repeats_keep_arriving():
    detector = HoldDetector(release_gap_seconds=0.25)
    detector.press(now=0.0)
    detector.press(now=0.05)
    detector.press(now=0.10)
    assert detector.is_held(now=0.20)


def test_released_after_the_gap_elapses():
    """Release is detected once repeats stop.

    The original version of this test asserted release 0.40s after a SINGLE
    press. That encoded an assumption this machine's settings disprove: the
    first auto-repeat does not arrive until 500ms, so at 0.40s the key is still
    held and no repeat has been seen yet. The wait is measured from the last
    repeat, not from the first press.
    """
    detector = HoldDetector(release_gap_seconds=0.25)
    detector.press(now=0.0)     # initial press
    detector.press(now=0.50)    # first auto-repeat
    assert not detector.is_held(now=0.90)


def test_not_held_before_any_press():
    assert not HoldDetector().is_held(now=1.0)


def test_held_through_the_initial_repeat_delay():
    """The first auto-repeat arrives only after the initial delay (500 ms on
    this machine). The key is still held throughout that window."""
    d = HoldDetector()
    d.press(now=0.0)
    for t in (0.10, 0.24, 0.26, 0.40, 0.49):
        assert d.is_held(now=t), f"reported released at {t}s while still held"


def test_release_detected_promptly_once_repeats_are_flowing():
    d = HoldDetector()
    d.press(now=0.0)          # initial press
    d.press(now=0.50)         # first repeat
    d.press(now=0.53)         # second repeat
    assert d.is_held(now=0.55)
    assert not d.is_held(now=0.90), "should detect release soon after repeats stop"


def test_real_system_repeat_stream_stays_held_throughout():
    """Replay this machine's actual timing: first repeat at 500 ms, then 30 ms."""
    d = HoldDetector()
    times = [0.0] + [0.5 + i * 0.03 for i in range(20)]
    for i, t in enumerate(times):
        d.press(t)
        if i + 1 < len(times):
            midpoint = (t + times[i + 1]) / 2
            assert d.is_held(midpoint), f"dropped the hold at {midpoint:.3f}s"


def test_release_resets_the_hold():
    d = HoldDetector()
    d.press(now=0.0)
    d.release()
    assert not d.is_held(now=0.01)
