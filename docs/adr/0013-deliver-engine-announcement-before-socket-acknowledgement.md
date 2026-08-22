# 0013 — Deliver engine announcement before socket acknowledgement

## Status

Accepted (2026-08-23)

## Context

Task 13's required test expects the announcement callback to have completed
when the socket client receives `ok`, while its reference code starts that
callback in a background thread after sending the response. This is a race.

## Decision

Invoke `on_announce` synchronously before returning the socket success reply.

## Consequences

Socket success now truthfully means the callback accepted the text. A later
engine layer may provide its own bounded asynchronous speech work; this narrow
service no longer makes a timing promise it cannot satisfy.
