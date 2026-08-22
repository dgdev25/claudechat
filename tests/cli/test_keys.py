from claudechat.cli.keys import HoldDetector


def test_held_while_repeats_keep_arriving():
    detector = HoldDetector(release_gap_seconds=0.25)
    detector.press(now=0.0)
    detector.press(now=0.05)
    detector.press(now=0.10)
    assert detector.is_held(now=0.20)


def test_released_after_the_gap_elapses():
    detector = HoldDetector(release_gap_seconds=0.25)
    detector.press(now=0.0)
    assert not detector.is_held(now=0.40)


def test_not_held_before_any_press():
    assert not HoldDetector().is_held(now=1.0)
