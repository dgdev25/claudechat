# Handover — claudechat phase 1, Tasks 3 to 16

You are taking over implementation of `claudechat`. Tasks 1 and 2 are done and committed.
Tasks 3 to 16 are yours. This document is written for someone with no prior context on this
project. Read it fully before writing code.

A reviewer will go over your work afterwards and fix what needs fixing. That is not a reason
to be careless: the review costs far less when the work is right, and the traps listed in
section 7 have already cost real rework once each.

---

## 1. What this project is

`claudechat` gives Claude a voice on one Linux workstation. It speaks Claude's replies aloud
through the speakers and transcribes the user's speech through a microphone.

Two surfaces:

- **A terminal voice client.** The user records a question, it is transcribed locally, sent to
  Claude, and the reply is spoken aloud sentence by sentence as it streams in.
- **A Claude Code hook.** When an interactive Claude Code session finishes a reply, a short
  spoken summary is read aloud.

Hard requirements that shape everything:

- **All speech is local and runs on the CPU.** No cloud speech service, no GPU, no CUDA.
- **Claude is reached through the Claude Code CLI**, not the API and not the Agent SDK,
  because the CLI reuses the user's existing OAuth subscription login. There is no API key
  anywhere in this project.
- **No paid services and no new dependencies** beyond those already pinned.

A browser client and a hands-free listening mode are explicitly **out of scope** for phase 1.
Do not build them, and do not add hooks "ready for" them.

---

## 2. Read these, in this order

| Path | What it is |
|---|---|
| `docs/superpowers/plans/2026-08-22-claudechat-phase-1.md` | **Your task list.** 16 tasks, each with the exact code and tests to write. This is the authority on *what to build*. |
| `docs/PRD.md` | The numbered requirements (`REQ-001` … `REQ-028`). Every task cites the ones it satisfies. |
| `docs/superpowers/specs/2026-08-22-claudechat-voice-design.md` | The design, the measured latency budget, and the security design in section 6. |
| `docs/adr/0001` … `0009` | Nine decision records explaining *why* each major choice was made. Read `0002`, `0005`, `0006` and `0009` before touching Claude invocation, speech synthesis, the hook, or the socket. |

Per-task briefs have already been extracted to individual files so you do not have to read the
whole plan each time:

```
.superpowers/sdd/docs-superpowers-plans-2026-08-22-claudechat-phase-1/task-<N>-brief.md
```

There is also `global-constraints.md` in that directory, and `progress.md`, which is the
running ledger of what is done.

---

## 3. Current state

Branch: `feat/voice-engine-phase-1`. Do not work on `main`.

Committed and complete:

- **Task 1** — `pyproject.toml`, `src/claudechat/config.py` (`Config`, `load_config`). 5 tests.
- **Task 2** — `src/claudechat/text/strip.py` (`strip_control_characters`, `SpeechStripper`).
  7 tests. A review of this task was in flight at handover; if it produced findings, they will
  be listed in `progress.md`. Check there before assuming Task 2 is settled.

Full suite currently: **12 passed**. Keep it green. If you make it red, fix it before moving
on — never leave a broken suite for the next task.

Everything from Task 3 onward does not exist yet.

---

## 4. Environment, already verified on this machine

Do not re-derive these. They were measured, not assumed.

- Python **3.13** via `uv`. **Never use `pip` or the system Python.** Run everything as
  `uv run …` (e.g. `uv run pytest -q`). `uv.lock` is committed; keep it in sync if you ever
  change dependencies, which you should not need to.
- `pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`. Plain test modules
  work; **no `__init__.py` is needed in test directories.**
- Audio is **PipeWire 1.6.2**. Use `pw-record` and `pw-play`, **not** `arecord`/`aplay` —
  direct ALSA access bypasses PipeWire routing. `pactl` is not installed.
- The Claude CLI is at `~/.local/bin/claude`, version 2.1.240, already logged in via OAuth.
- Test markers already registered: `slow` (needs model files) and `live` (spends Claude quota).
  Use them. A test that downloads 340 MB of models or calls Claude must be marked.

Measured performance targets, for reference when you reach Task 16:

| Stage | Measured | Source |
|---|---|---|
| Kokoro synthesis | real-time factor 0.168; 0.32 s for a short sentence | benchmarked on this CPU |
| `base.en` transcription | 0.21 s for a 3.67 s clip | benchmarked on this CPU |
| Claude first complete sentence | 2.57 s | measured via the CLI |
| **Total to first audio** | **≈3.1 s** against a 3.5 s target | sum of the above |

---

## 5. Global constraints — these bind every task

Copied from the plan. Violating any of these is a defect regardless of whether a task's brief
repeats it.

- **CPU only.** Use `onnxruntime`, never `onnxruntime-gpu`. `compute_type="int8"` for
  faster-whisper. No CUDA imports anywhere.
- **Subprocesses: `shell=False`, an explicit argv list, an absolute executable path, and a
  minimal environment.** Never `shell=True`. Never `shlex.split()` on a config value.
- **The Claude CLI flag set is fixed and mandatory.** Every invocation uses exactly:
  `--output-format stream-json --verbose --include-partial-messages --model sonnet
  --strict-mcp-config --mcp-config '{"mcpServers":{}}' --tools "" --disable-slash-commands
  --exclude-dynamic-system-prompt-sections --system-prompt <persona>
  --settings '{"enabledPlugins":{}}'`.
  This is not style. It cuts per-turn context from 32,534 tokens to 3,489 — a ninefold saving
  on every turn (ADR 0002). **Never add `--permission-mode dontAsk`**: it is fail-open, and the
  design deliberately fails closed (ADR 0009).
- **The prompt goes on stdin, never in argv.** Command arguments are readable by any local
  process via `/proc`, and prompts contain the user's speech.
- **Every Claude subprocess starts with `start_new_session=True`** and is terminated by
  signalling the **process group**, escalating `SIGTERM` → `SIGKILL`. Signalling the bare
  process leaves Node children alive.
- **Audio is 16 kHz, mono, signed 16-bit little-endian** everywhere, except Kokoro's native
  output rate, which is resampled at the boundary.
- **Terminal presentation is fixed** — do not invent your own. State line is `● recording` /
  `◐ transcribing` / `◇ thinking` / `▶ speaking` / `○ idle`. User speech is prefixed `you:`,
  Claude's reply `claude:`. No colour beyond default plus dim. No spinners, no progress bars,
  no boxes. All external text passes through `strip_control_characters` before printing.
- **Never write raw prompt or reply text to a file** unless `debug_logging` is enabled.
- **Licences: MIT / Apache-2.0 / BSD / ISC only.** Do not add a dependency that is not already
  in `pyproject.toml`. If you believe you need one, stop and escalate (section 9).

---

## 6. How to work each task

For each task N from 3 to 16, in order:

1. **Read** `task-<N>-brief.md`. It contains the exact file paths, the code, and the test
   cases. Where it gives literal values — numbers, signatures, test inputs — use them verbatim.
   They are chosen to fit tasks you have not read yet.
2. **Write the tests first**, run them, and watch them fail for the right reason.
3. **Implement** the minimum that makes them pass.
4. **Run the whole suite**, not just your file: `uv run pytest -q`.
5. **Mutation-check your most important tests** (see 7.1 — this is not optional).
6. **Self-review your own diff** before committing. Remove anything the brief did not ask for.
7. **Commit** with the message the brief gives.
8. **Append to the ledger** at
   `.superpowers/sdd/docs-superpowers-plans-2026-08-22-claudechat-phase-1/progress.md`:
   `Task <N>: complete (commits <base7>..<head7>) — <one line on anything notable>`.
9. **Write a short report** to `…/task-<N>-report.md`: what you built, the test command and its
   output, your mutation-check evidence, any deviation from the brief and why.

Task order matters. Tasks 5 and 6 need Task 4's interfaces; Task 10 needs Task 9; Tasks 11 and
16 need almost everything. Do not skip ahead.

### Dependency map

```
1 config ─┬─► 4 speech interfaces + model download ─┬─► 5 synthesizer ─┐
          │                                          └─► 6 transcriber ─┤
          ├─► 8 capture                                                 │
          ├─► 9 ClaudeRunner ──► 10 Conversation ───────────────────────┤
          └─► 13 socket service ──► 14 announcer                        │
2 strip ──┴─► 3 chunker ─────────────────────────────────────────────────┤
7 playback ──────────────────────────────────────────────────────────────┤
                                                                         ▼
                                    11 terminal client ──► 12 keys ──► 16 wire-up
                                                        15 hook script ──┘
```

---

## 7. Traps already discovered — do not rediscover them

### 7.1 A test that passes for the wrong reason (cost two rework rounds in Task 1)

Task 1 shipped a test that appeared to verify config validation. It passed because the TOML
parser raised an error *before* the validation was ever reached, and the test's `except` clause
caught that too. Deleting the entire validation left the test green.

**So: for every test that asserts something is removed, rejected, or prevented, mutation-check
it.** Break the logic deliberately, confirm the test FAILS, restore the logic, confirm it
passes. Put that evidence in your report. Tests that matter most here:

- Task 3: that a sentence is not split on an abbreviation or a decimal point.
- Task 4: that a wrong digest is rejected and leaves no file behind.
- Task 7: that cancelling actually stops playback within 300 ms.
- Task 8: that the recording duration limit fires.
- Task 13: that an oversized body and unknown fields are rejected.
- Task 14: that code and URLs never reach the model call.
- Task 15: that the internal marker suppresses the hook.

Related: TOML accepts the six-character escape sequence `` and decodes it to a real
control character, but rejects a raw control byte at parse time. If you need a control
character inside a TOML fixture, write the escape sequence.

### 7.2 The Stop hook fires on our own Claude calls (would have shipped a loop)

This is the single most important behavioural trap in the project, and it is verified, not
theoretical.

The app calls `claude -p` itself. Those calls **also trigger the user's Stop hook**. Without a
guard, the app speaks every chat reply twice — once from its own stream and once from the hook —
and the hook's summarising call triggers the hook again, summarising its own summary.

The guard (ADR 0006, Tasks 9, 15, 16): the engine generates a random token at startup, writes it
to a `0600` file in its runtime directory, and passes it as `CLAUDECHAT_INTERNAL` on every CLI
process it spawns. The hook script compares the environment variable against the file and exits
0 immediately on a match. **Verified: the environment variable does reach the hook process.**

This is recursion control, not access control. Do not describe it as a security boundary.

### 7.3 Killing the process, not the group, orphans Node children

`claude` is a Node process that spawns children. `process.kill()` leaves them running, and they
accumulate. Always `os.killpg(os.getpgid(pid), …)`, and always spawn with
`start_new_session=True`. The same applies to `pw-play` and `pw-record`.

After any task that spawns a subprocess, check:

```bash
pgrep -a -f "claude -p" || echo "clean"
pgrep -a -f "pw-record" || echo "clean"
```

### 7.4 Cancelling playback is three actions, not one

Dropping newly-arriving audio chunks is not enough — audio already handed to the device keeps
playing. Cancellation must: stop generating, discard queued chunks, **and terminate `pw-play`
so the device buffer is flushed**. The 300 ms target in Task 7 is real; measure it.

### 7.5 Hook text is untrusted input to a model call

`last_assistant_message` can contain text that originated in repository files, tool output, or
web pages. When Task 14 sends it to Claude for summarising, it is untrusted data, not
instructions. It must be wrapped in `<untrusted_reply>` delimiters with a system prompt stating
the content must never be followed as instructions, and code, URLs, and credential-shaped
strings must be stripped **before** the call. The call stays tool-free so a successful injection
can only change spoken wording, never take action.

### 7.6 Model files are executable graphs

The ONNX files are parsed by native code, so a substituted file is a code-execution path. Task 4
pins SHA-256 digests. **Step 6 of Task 4 requires you to fetch the real digests and paste them
in.** The code tolerates an empty digest so tests can run — shipping it that way silently
disables the integrity check. Do not skip that step.

### 7.7 Do not commit scratch files

`git add -A` once swept tool scratch directories into a commit. `.gitignore` now covers
`.superpowers/`, `.claude-flow/`, `.swarm/`, `*.rvf`, `ruvector.db`, `models/`, `*.onnx`,
`*.bin`, `*.wav`, `.venv/`. Check `git status --short` before committing and stage deliberately.

---

## 8. Definition of done for a task

All of these, or the task is not done:

- [ ] Every requirement in the brief is implemented, with the brief's literal values.
- [ ] Nothing implemented that the brief did not ask for.
- [ ] Tests from the brief exist and pass.
- [ ] The important tests are mutation-checked, with evidence in the report.
- [ ] The whole suite passes (`uv run pytest -q`), not just the new file.
- [ ] No orphaned processes after tasks that spawn subprocesses.
- [ ] Committed with the brief's message; no scratch files staged.
- [ ] Ledger line appended; report file written.

---

## 9. Stop and escalate rather than deciding these yourself

Write what you found and why you stopped; do not improvise around any of them.

- A brief contradicts this document, the plan's global constraints, or an ADR.
- You believe you need a dependency that is not already in `pyproject.toml`.
- A brief's literal value looks wrong for a later task.
- The Claude CLI's flags or its stream-json output shape differ from what section 5 describes
  (this would mean the CLI changed under us — a real risk noted in ADR 0001).
- **Task 12 specifically.** It measures whether hold-to-talk is possible in this terminal.
  Terminals report key presses, not releases, and this machine's terminal (VTE 0.84) has no
  enhanced keyboard protocol. Run the measurement in step 5, record the real result, and take
  the branch the result dictates. **Do not force hold-to-talk if the measurement says it is
  not viable** — the fallback to press-to-start / press-to-stop is already agreed and is a
  legitimate outcome, not a failure. Record which path you took in ADR 0008's consequences.
- Any task where a correct implementation would require deviating from the plan. Deviation may
  well be right — but it needs recording as a decision (an ADR), not a silent change.

---

## 10. When you finish

Report back with:

1. Which tasks completed, with commit ranges.
2. Total test count and the suite's final state.
3. The Task 16 benchmark numbers against the section 4 targets — and say plainly if a target
   was missed rather than presenting a miss as a pass.
4. The Task 12 outcome: hold-to-talk or toggle.
5. Anything you deviated from, with the reason.
6. Anything you were unsure about and decided anyway — this is the most useful thing you can
   tell the reviewer.

Do not claim a task is complete if its tests are skipped, its mutation check was not run, or
the suite is red. An honest "Task 14 is done but its injection test is weak" is worth far more
than a confident green tick that does not hold up.
