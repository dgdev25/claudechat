# 0004 — Write the engine in Python rather than a compiled language

## Status

Accepted (2026-08-22)

## Context

The user asked whether Rust would make the app faster. The question was settled by profiling
rather than opinion. Of 2.981 s spent synthesising three sentences, 2.975 s — 99.8 % — was
inside a single native ONNX Runtime call, and all Python glue across the run totalled 6 ms.
Speech-to-text is likewise native code in CTranslate2. Rust bindings would call the same
kernels.

## Decision

Implement the engine in Python, pinned to 3.13 via `uv`.

## Consequences

Good: fastest route to a working engine; the mature bindings for Kokoro and faster-whisper
are Python; iteration stays quick while the design is still being proven.

Bad: requires a virtual environment rather than shipping a single binary; audio buffering
through subprocesses has more jitter than a native audio library would; and Python threading
constrains concurrency, though the native calls release the interpreter lock.

Because speech sits behind narrow interfaces, porting the audio layer or the hot path later
stays cheap. Revisit if a single distributable binary or lower audio jitter becomes a
requirement — not for throughput, which the profile shows would gain about one millisecond
per turn.

## Alternatives

- Rust — rejected for performance, since 99.8 % of the time is already native C++. It remains
  the right answer if a single static binary or Wayland global hotkey capture becomes
  necessary; `voxtype` is the precedent.
- Node.js — rejected: the Kokoro and faster-whisper bindings are weaker, and the audio and
  ONNX ecosystem is less mature than Python for this work.
