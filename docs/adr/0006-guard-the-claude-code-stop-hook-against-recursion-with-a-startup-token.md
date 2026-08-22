# 0006 — Guard the Claude Code Stop hook against recursion with a startup token

## Status

Accepted (2026-08-22)

## Context

The app both drives `claude -p` itself and registers a `Stop` hook to speak replies from
interactive sessions. Testing on this machine confirmed that the hook fires for the apps own
headless calls as well as for the users interactive ones. Without a guard the app would speak
each chat reply twice — once from its own stream and once from the hook — and the summarising
call would itself trigger the hook, producing a summary of a summary and potentially an
unbounded loop.

Testing also confirmed that an environment variable set on the spawned CLI process does reach
the hook process, so the guard mechanism works.

## Decision

The engine generates a random token at startup and stores it in a `0600` file in its runtime
directory. Every CLI process the app spawns carries that token in `CLAUDECHAT_INTERNAL`. The
hook script reads the stdin payload only after comparing the variable against the stored
token; on a match it exits 0 immediately.

## Consequences

Good: removes duplicate speech and the summary-of-summary loop; costs one comparison at the
top of the hook script; verified to work.

Bad: it is recursion control and not access control — any process able to run the hook could
set the variable and suppress announcements. A random per-start token rather than a fixed `1`
prevents an unrelated exported variable from silently muting the app, but it does not make
this a security boundary, and the design says so explicitly.

## Alternatives

- A fixed `CLAUDECHAT_INTERNAL=1` — rejected: a stray export in the users shell profile would
  silently disable all spoken summaries with no diagnostic.
- Deduplicate by comparing reply text — rejected: fragile, needs state, and fails when two
  genuinely identical replies occur.
- Register no hook and poll the transcript files — rejected: more work and more fragile than
  the payload the hook already provides.
