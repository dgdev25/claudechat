# 0010 — Deviate from the plan reference stripper to close four defects

## Status

Accepted (2026-08-23)

## Context

Task 2 built the text stripper that removes markdown, code, URLs, and terminal control
characters before text is spoken aloud or printed. The implementation was copied verbatim from
the plans reference code, as the plan instructed. Review then found four defects in that
reference code itself:

- Only backtick fences were recognised, so a `~~~` fenced code block was spoken verbatim — the
  exact failure the module exists to prevent.
- The emphasis rule stripped every underscore, so `variable_name_here` became
  `variablenamehere`. This tool speaks a coding assistants output aloud, so identifiers are
  among the most common words it will ever say.
- The table, list-marker, and link rules had no test at all; deleting any of them left the
  whole suite green.
- 8-bit C1 control codes (`\x80-\x9f`) bypassed both escape patterns, and some terminals honour
  them — relevant because this function is the only defence against escape-sequence injection
  from untrusted hook text.

## Decision

Deviate from the plans reference implementation. Recognise both backtick and tilde fences while
tracking which character opened the fence so a fence can only be closed by its own character;
apply CommonMarks intraword rule so underscores inside a word are preserved; strip the C1
control range; and add tests for the three untested rules.

Three known gaps are deliberately NOT fixed and are recorded as accepted: unterminated OSC
sequences leak visible text (the leading escape byte is still stripped, so this is noise rather
than an injection risk), unterminated inline-code spans leave a literal backtick, and indented
four-space code blocks are not treated as code. The last was rejected because stripping
four-space indents would eat ordinary prose, which is a worse failure than the one it fixes.

## Consequences

Good: code fences of both kinds are now suppressed; identifiers are spoken correctly; the
escape-stripping covers 8-bit forms; and every rule in the module has a test that fails when
that rule is removed, verified by mutation.

Bad: the implementation now diverges from the plan text, so the plans Task 2 code block is
stale and should not be used as a reference. The three deferred gaps remain and are listed
above rather than being quietly forgotten.

The wider consequence is a process one: the plans reference code is a first draft, not a
specification of internal logic. Later tasks must treat its interfaces and literal values as
binding but review its logic — recorded in the Codex handover as trap 7.7.

## Alternatives

- Ship the reference code unchanged — rejected: it read source code aloud, defeating the
  modules purpose.
- Replace the hand-written regexes with a markdown parsing library — rejected: every candidate
  is GPL, drags in an HTML parser, or is built for rendering rather than for speech, and none
  handles text arriving in fragments.
- Also strip indented four-space blocks — rejected: too many false positives on ordinary prose.
