# 0011 — Deviate from the plan reference chunker ordering

## Status

Accepted (2026-08-23)

## Context

Task 3 requires the first chunk of a response to be released at a qualifying
comma, to reduce time to first audio. Its supplied test passes the complete
sentence `"Yes I can help with that, and here is why it matters. "` in one
fragment and expects the comma-delimited chunk first.

The supplied reference implementation looks for a sentence terminator before
it considers early first-chunk boundaries. Consequently it emits the complete
sentence and fails the task's own test.

## Decision

For the first chunk only, check qualifying comma and word-count boundaries
before sentence terminators. Once an early chunk is emitted, later chunks use
sentence terminators only, as specified by the task.

## Consequences

The implementation meets both the latency requirement and the task test while
retaining the supplied public interface and literal thresholds. The plan's
reference code block is stale in this ordering and must not be copied
verbatim.

## Alternatives

- Preserve the reference ordering — rejected because it fails the stipulated
  early-comma behaviour.
- Change the test to stream the input in smaller fragments — rejected because
  streaming fragment boundaries are not a behavioural guarantee and the
  existing test exposes the ordering defect directly.
