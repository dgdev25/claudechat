# 0005 — Use Kokoro for speech synthesis, accepting a GPL phonemizer dependency

## Status

Accepted (2026-08-22)

## Context

The project prefers permissively licensed dependencies. Research found that most good local
neural speech synthesis depends on espeak-ng for phonemization, and espeak-ng is GPL-3.0.
Verified by resolving the dependency tree: `kokoro-onnx` 0.6.1 pulls `phonemizer` 3.4.0
(GPL-3.0) and `espeakng-loader` (which ships espeak-ng binaries) as hard dependencies, not as
a separate process.

The alternatives are no cleaner. Piper on PyPI is now GPL-3.0-or-later and its maintained
repository is literally named `piper1-gpl`; the MIT `rhasspy/piper` has been archived since
August 2025. KittenTTS, kokoro-js, and the sherpa-onnx prebuilt binaries all carry espeak-ng
transitively. Supertonic is the only espeak-free option found, but its weights are
OpenRAIL — use-restricted, not permissive — and its repository is scheduled for archival.

This is a personal tool for one machine. GPL obligations attach to conveying software, not to
running it, so no obligation arises from use.

## Decision

Use `kokoro-onnx` with Apache-2.0 Kokoro weights, accepting the GPL-3.0 `phonemizer` and
`espeakng-loader` dependencies. Record the constraint that this must be revisited before any
public distribution.

## Consequences

Good: the best measured combination of voice quality and CPU speed (real-time factor 0.168);
Apache-2.0 model weights; an actively maintained wrapper.

Bad: the project cannot be distributed under a permissive licence as it stands. Publishing it
would require either relicensing the whole work under GPL-3.0, or replacing the phonemizer —
for example with `misaki` (Apache-2.0), which still falls back to espeak for out-of-vocabulary
words. This is a known, recorded debt rather than an oversight.

## Alternatives

- Piper — rejected: the maintained fork is GPL-3.0, so it carries the same constraint with
  lower voice quality; the MIT version is archived and unmaintained.
- Supertonic — rejected: OpenRAIL weights are use-restricted, failing the licence rule more
  severely than GPL, and the repository is being archived.
- espeak-ng as a subprocess only — rejected as a false comfort: the Python package pulls the
  library in directly, and the process boundary argument is a judgement call rather than a
  clean separation.
