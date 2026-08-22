# 0007 — Build one process with speech behind narrow interfaces

## Status

Accepted (2026-08-22)

## Context

An earlier design put the web server, Claude subprocess management, and both GPU speech models
in one process. Two independent model reviews rejected that: faster-whisper uses CTranslate2
and Kokoro uses ONNX Runtime, both native, and a CUDA crash or a CUDA/cuDNN version conflict in
either would take down the whole application, which Python cannot catch. The design was
revised to a supervised speech worker in a separate process.

The subsequent CPU-only decision (ADR 0003) removed CUDA from the picture, and with it the
main justification for the split. Retaining a two-process architecture would have meant paying
for inter-process plumbing to solve a failure mode that no longer exists.

## Decision

Run one process. Put transcription and synthesis behind two narrow interfaces —
`transcribe(pcm, sample_rate) -> str` and `synthesize(text) -> (audio, sample_rate)` — and run
them on a thread pool so the terminal stays responsive.

## Consequences

Good: much less machinery — no socket protocol, no supervisor, no health checks, no restart
policy — for a single-user desktop tool. Native calls release the interpreter lock, so the
thread pool is genuinely concurrent.

Bad: a native crash in either speech library still takes down the application. The reviews
noted that ONNX Runtime and CTranslate2 can still fail on malformed input even without CUDA.
This is accepted because the blast radius is one users foreground tool that can be restarted,
not a service. The narrow interfaces keep a later split cheap if it proves necessary.

## Alternatives

- Two processes with a supervised speech worker — rejected once CPU-only removed the CUDA
  failure mode it was designed to contain. Reconsider if native crashes prove common.
- Three services behind HTTP, as `voicemode` does — rejected: three things to install and
  supervise for one desktop user, with per-request HTTP latency and awkward sentence-level
  streaming.
