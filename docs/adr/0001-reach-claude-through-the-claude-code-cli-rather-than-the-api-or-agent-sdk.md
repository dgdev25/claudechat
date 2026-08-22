# 0001 — Reach Claude through the Claude Code CLI rather than the API or Agent SDK

## Status

Accepted (2026-08-22)

## Context

The app needs to send prompts to Claude and read replies. Three routes exist: the Anthropic
Messages API, the Claude Agent SDK, and the Claude Code CLI in headless mode. The user has a
Claude subscription and an existing OAuth login, and stated they do not want to use an API
key. Research confirmed the Agent SDK requires `ANTHROPIC_API_KEY` and cannot use the OAuth
session. A community project claimed headless CLI use is billed as metered agent credits
rather than the flat subscription.

That billing claim was tested on this machine: the `rate_limit_event` reported
`rateLimitType: "five_hour"` with `isUsingOverage: false`, showing the call drew on the
normal subscription window. The claim did not hold.

## Decision

Drive Claude through `claude -p` in headless mode with `--output-format stream-json`, using
the existing OAuth login. Do not use the Messages API or the Agent SDK.

## Consequences

Good: no API key to store or leak; no per-token billing beyond the existing subscription;
streaming text is available for early speech; the `Stop` hook integrates the same backend
with interactive sessions.

Bad: the app depends on an internal CLI output format that Anthropic may change without
notice, and on flag names that may be renamed. A parser guarding on event type is required,
and CLI upgrades must be treated as a compatibility risk. Process startup adds latency to
every turn compared with an in-process SDK call.

## Alternatives

- Anthropic Messages API — rejected: requires an API key and bills separately from the
  subscription the user already pays for.
- Claude Agent SDK — rejected: verified to require `ANTHROPIC_API_KEY`, so it cannot reuse
  the OAuth session, which was the users explicit requirement.
