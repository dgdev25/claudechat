# 0003 — Run all speech models on the CPU with no GPU dependency

## Status

Accepted (2026-08-22)

## Context

The machine has an RTX 4090 with 24 GB, and the initial design used CUDA for both speech
models. The user then required that nothing depend on a GPU. Benchmarks were run on CPU only:
Kokoro synthesis reached a real-time factor of 0.168 with a short sentence produced in 0.32 s,
and faster-whisper `base.en` transcribed a 3.67 s clip in 0.21 s. Total time to first audio
was about 3.1 s, of which 2.57 s was Claude generating the reply.

## Decision

Target CPU execution only. Use `onnxruntime` rather than `onnxruntime-gpu`, and CTranslate2
on CPU with int8 quantisation. Do not require CUDA at any point.

## Consequences

Good: the app runs on any machine, survives driver changes, leaves the GPU free for other
work, and removes CUDA/cuDNN version conflicts between CTranslate2 and ONNX Runtime — which
was the main justification for an earlier two-process design, so this decision also simplified
the architecture.

Bad: larger transcription models become impractical, capping accuracy at roughly `base.en`
quality. Speech competes with other CPU work. Throughput would be higher on the GPU, though
measurement shows the difference is hidden behind Claude latency.

## Alternatives

- CUDA with CPU fallback — rejected: two code paths to test and the fallback would be the
  rarely exercised one, so it would rot.
- GPU-only — rejected by the users explicit constraint, and unnecessary given the measurements.
