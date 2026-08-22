# 0008 — Deliver the terminal client first and defer the browser client

## Status

Accepted (2026-08-22)

## Context

The user asked for both a browser interface and a terminal interface. They then asked to prove
the engine works in the terminal first and pause the browser work. The engine — capture,
transcription, the Claude turn, text handling, synthesis, playback, interruption — is shared by
both surfaces; only capture and presentation differ.

A constraint reinforces this order. Terminal emulators report key presses but not releases, and
this machine runs VTE 0.84 with no enhanced keyboard protocol, so hold-to-talk may not be
achievable in the terminal. A browser has reliable keydown and keyup events, so it is the
surface that can deliver true hold-to-talk.

## Decision

Phase 1 delivers the engine, the terminal client, and the Claude Code hook. The browser client
(REQ-027) and hands-free voice detection (REQ-028) are deferred to phase 2.

## Consequences

Good: a working, testable engine sooner, with the risky parts — interruption, process cleanup,
hook recursion — proven before a second surface is added. Hands-free mode is deferred along
with the echo, endpointing, and false-trigger problems it brings.

Bad: hold-to-talk, the interaction the user originally asked for, may not be available in
phase 1; the terminal client may need press-to-start / press-to-stop instead. That gap is
stated openly rather than papered over, and phase 2 closes it. Adding the browser client later
also means the security model gains a network listener, which must be threat-modelled at that
point.

Task 12 outcome (2026-08-23): use press-to-start / press-to-stop toggle mode. The prescribed
auto-repeat probe could not access a TTY in the automated execution channel (`ENOTTY`), so it
did not produce a repeat interval. With VTE 0.84 and no enhanced keyboard protocol, this does
not establish reliable hold-to-talk; the agreed fallback is used. A manual probe in the user's
interactive VTE session remains the only way to revise this decision.

## Alternatives

- Both surfaces at once — rejected by the user, and it would double the surface area before
  the engine is proven.
- Browser first — rejected: the user works in the terminal and wanted the engine proven there.
