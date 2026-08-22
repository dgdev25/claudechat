# 0012 — Inject terminal recording stop signal for testability

## Status

Accepted (2026-08-23)

## Context

Task 11's supplied terminal-client reference calls `input()` inside
`VoiceSession.run_turn()`. Pytest replaces stdin while capturing output, so a
unit test of `run_turn()` raises an `OSError` before it can exercise the
recording, transcription, or conversation flow.

## Decision

`VoiceSession` accepts a final `wait_for_stop` callable, defaulting to
`input`. `run_turn()` invokes that callable. Production construction leaves
the default unchanged; tests supply a no-op callable.

## Consequences

The interactive behavior remains Enter-to-stop recording. The per-turn method
is testable without disabling pytest capture. This is the controller-approved
correction to the Task 11 reference implementation.

## Alternatives

- Call `input()` directly — rejected because the required unit test cannot run.
- Disable pytest output capture — rejected because it changes test execution
  globally instead of making the dependency explicit.
