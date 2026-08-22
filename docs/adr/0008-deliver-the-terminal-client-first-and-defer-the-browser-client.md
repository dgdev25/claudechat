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

Task 12 outcome (2026-08-23), SUPERSEDED — see below.
The automated probe could not access a TTY (`ENOTTY`), produced no repeat interval, and the
agreed toggle fallback was taken on that basis. That reasoning was sound given what was
measurable from a non-interactive channel.

Task 12 outcome (2026-08-23, final): hold-to-talk IS viable. The repeat timing did not need a
TTY at all — it is a system setting, read directly:

    org.gnome.desktop.peripherals.keyboard delay            = 500 ms
    org.gnome.desktop.peripherals.keyboard repeat-interval  =  30 ms

30 ms is far inside the 200 ms threshold this plan set, so auto-repeat inference is reliable
here and no manual probe is required. Reading the settings also exposed a defect in the
reference detector, fixed in ADR 0014.

Remaining work: the terminal client still runs press-to-start / press-to-stop. The detector
now supports holding correctly, but wiring `read_key_events` into `run_turn` was not done and
is outstanding.
