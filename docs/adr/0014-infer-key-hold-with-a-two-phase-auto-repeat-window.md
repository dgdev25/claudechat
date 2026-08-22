# 0014 — Infer key hold with a two-phase auto-repeat window

## Status

Accepted (2026-08-23)

## Context

Task 12 asks whether hold-to-talk is achievable in the terminal. Terminals report key presses
but not releases, so holding must be inferred from auto-repeat, and the plan left the answer
to a manual measurement in which a human holds the spacebar.

That measurement was not needed. The timing is a system setting and was read directly:

    gsettings get org.gnome.desktop.peripherals.keyboard delay            -> 500 ms
    gsettings get org.gnome.desktop.peripherals.keyboard repeat-interval  -> 30 ms

Repeats arrive every 30 ms, far inside the 200 ms threshold the plan set, so hold-to-talk IS
viable on this machine.

The same reading exposed a defect in the reference detector. It used one release gap of
250 ms, measured from the last press. Because the first repeat does not arrive until 500 ms,
the detector reports the key released between 250 ms and 500 ms while the user is still
holding it. Recording would cut out on every press. Confirmed by replaying the real timing
against the committed code.

## Decision

Infer holding with a two-phase window instead of a single gap. Until the first repeat arrives,
tolerate an initial-delay-sized gap (the configured delay plus a quarter for jitter). Once
repeats are flowing, switch to an interval-sized gap (four repeat intervals, floored at
120 ms) so release is detected promptly. Both values are constructor parameters defaulting to
this machine s measured settings, and a release() method resets the hold.

The brief s own test `test_released_after_the_gap_elapses` asserted release 0.40 s after a
SINGLE press. That assertion encodes the disproved assumption and was corrected to measure the
wait from the last repeat rather than the first press, with the reason recorded in the test.

## Consequences

Good: hold-to-talk works without cutting out; release is detected within about 120 ms once
repeats flow, which is well inside the 300 ms barge-in target; the timing values are
injectable, so a machine with different keyboard settings can be configured rather than
patched; and no human measurement is required.

Bad: the defaults are this machine s settings, so a user with a much longer initial delay
would need to override them — the constructor takes the values, but nothing reads gsettings at
runtime. A future improvement is to read the two settings on startup and pass them in.

The measurement in the plan s Task 12 step 5 is now redundant and should not be run.

## Alternatives

- Keep one 250 ms gap — rejected: it drops the hold between 250 ms and 500 ms on every press,
  which is the whole interaction failing.
- Use one long gap above 500 ms — rejected: release would then lag more than half a second
  after the key is let go, adding silence to every turn and missing the barge-in target.
- Fall back to press-to-start / press-to-stop — rejected: the measurement shows hold-to-talk
  is achievable, and holding is what the user asked for.
- Require a terminal with the kitty keyboard protocol for true key-release events — rejected:
  this terminal (VTE 0.84) does not advertise it, and auto-repeat inference works.
