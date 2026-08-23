# PRD — claudechat

Status: draft
Date: 2026-08-22

## 1. Summary

`claudechat` gives Claude a voice on a single Linux workstation. It speaks Claude's replies
aloud through the speakers and listens to the user through a microphone. It has two
surfaces: a **terminal voice client** where the user holds a key, speaks, and hears the
answer; and a **Claude Code hook** that speaks a short summary of replies produced during
normal interactive Claude Code sessions. All speech runs locally on the CPU. The language
model is reached through the Claude Code CLI in headless mode, which reuses the user's
existing OAuth subscription login, so no API key and no paid third-party service is
required. It is built now because the user wants to hear and talk to Claude while working,
and the local speech models have become fast enough on CPU to make that comfortable.

## 2. Problem

Claude currently communicates only as text on screen. The user must read every reply and
type every prompt, which ties them to the keyboard and the terminal window. Two costs
follow:

- **Reading tax while working.** During a long Claude Code session the user reads many
  replies, most of which are status and reasoning they only need the gist of. They cannot
  step away from the screen or look at something else while Claude works.
- **Typing tax for conversation.** Ordinary questions are faster to ask aloud than to type,
  but there is no local way to do so.

Evidence from this machine: Claude Code ships a built-in `/voice` dictation feature which
the user has already enabled with `{"enabled": true, "mode": "hold"}`, showing demand for
voice input. It has no counterpart for output — nothing speaks Claude's replies. Existing
third-party options fail on at least one of: requiring a paid cloud TTS service, requiring
an API key instead of the subscription login, shipping no LICENSE file, or being GPL/AGPL.

## 3. Personas

- **The working developer (primary).** Job: keep making progress on code while Claude Code
  runs, without having to watch the terminal for every reply.
- **The hands-busy thinker (primary).** Job: ask Claude a question aloud and get a spoken
  answer, without breaking off what they are doing to type.
- **The maintainer of this tool (secondary).** Job: change a speech engine, a voice, or a
  model without rewriting the application.

## 4. Goals & success metrics

| Goal | Metric | Target |
|---|---|---|
| Spoken replies feel prompt | Median time from key release to first audible word | ≤ 3.5 s |
| Speech layer is not the bottleneck | Median STT + TTS time, excluding Claude | ≤ 0.8 s |
| Transcription is accurate enough to trust | Word error rate on 20 held-out spoken prompts | ≤ 5 % |
| Runs without a GPU | Benchmarks pass with CUDA disabled | 100 % of runs |
| Conversation stays affordable | Context tokens billed per chat turn | ≤ 5,000 |
| Interrupting works | Time from barge-in keypress to audio silence | ≤ 300 ms |
| Hook never duplicates speech | Duplicate or recursive utterances per 50 hook turns | 0 |

### Measured result at end of phase 1 (2026-08-23) — TWO TARGETS MISSED

Median of three runs on an otherwise idle machine, measured the way the app actually
behaves (first speakable chunk, not a fixed sentence):

| Stage | Measured | Design estimate |
|---|---|---|
| Transcribe | 0.26 s | 0.21 s |
| Claude, to first complete chunk | 3.74 s (range 3.42–5.73) | 2.57 s |
| Synthesise that chunk | 0.84 s | 0.32 s |
| **Total to first audio** | **4.84 s — target ≤ 3.5 s, MISSED** | 3.1 s |
| **Speech layer only** | **1.10 s — target ≤ 0.8 s, MISSED** | 0.53 s |

Cause, not excuse. Claude is 77 % of the total and no local change touches it. The design
estimate of 2.57 s was a single lucky sample; the median over repeated runs is 3.74 s. The
synthesis estimate was measured on a 27-character sentence, whereas real first chunks run to
about 85 characters because the early-comma rule only fires at the first comma, which is often
well into the sentence.

Two measured levers, neither yet applied:

1. **Process startup is 0.89 s of every turn** — measured as 0.89 s of the 1.66 s to first
   token, roughly half. A persistent headless process (open question 2) would recover it.
2. **Release the first chunk sooner.** `first_chunk_max_words` is 30. Lowering it shortens
   both the wait for a chunk boundary and the synthesis of that chunk, at some cost to
   phrasing.

Together these plausibly reach the 3.5 s target; neither alone does. Until one is applied the
honest figure is ≈4.8 s, and the targets above stand as unmet rather than being revised to
match the result.

Baseline measurements taken on this machine (Intel i9-14900K, CPU only) during design:
Kokoro TTS real-time factor 0.168 with first sentence in 0.32 s; faster-whisper `base.en`
transcribed a 3.67 s clip in 0.21 s; `claude -p` produced its first complete sentence in
2.57 s; total to first audio ≈ 3.1 s.

## 5. Functional requirements

### Speech engine (phase 1)

- **REQ-001** (P0) The system transcribes a recorded utterance to text locally, with no
  network call.
- **REQ-002** (P0) The system synthesises a given text to speech locally, with no network
  call, and plays it through the default output device.
- **REQ-003** (P0) The system runs entirely on the CPU and never requires a GPU or CUDA.
- **REQ-004** (P0) Speech-to-text and text-to-speech are each reached through a narrow
  interface, so an engine can be replaced without changing the orchestrator.
- **REQ-005** (P1) The transcription model, synthesis voice, and speaking rate are set in a
  configuration file without code changes.

### Terminal voice client (phase 1)

- **REQ-006** (P0) The user starts recording, speaks, and stops recording using the
  keyboard, and the client shows which state it is in.
- **REQ-007** (P0) On stopping the recording, the client transcribes the utterance, sends
  it to Claude, and speaks the reply.
- **REQ-008** (P0) The client displays the transcribed prompt and the reply text alongside
  speaking it, so a mis-transcription is visible.
- **REQ-009** (P1) The client speaks each sentence as it arrives rather than waiting for
  the complete reply.
- **REQ-010** (P1) The user can interrupt speech in progress; playback stops and any
  in-flight generation is abandoned.
- **REQ-011** (P1) Conversation context persists across turns within a session.
- **REQ-012** (P2) The user can quit cleanly, leaving no orphaned audio or model processes.

### Claude backend

- **REQ-013** (P0) Claude is reached through the Claude Code CLI in headless mode using the
  user's existing OAuth login; the system never requires an API key.
- **REQ-014** (P0) Each chat turn runs with project context, MCP servers, plugins, skills,
  and tools disabled, to keep per-turn context small.
- **REQ-015** (P0) Assistant text is consumed as a stream so speech can begin before the
  reply is complete.
- **REQ-016** (P0) When a turn is abandoned, the CLI process and all of its child processes
  are terminated, leaving none running.
- **REQ-017** (P1) Only one Claude turn is active per conversation at a time; a new turn
  starts only after the previous process has fully exited.

### Claude Code hook (phase 1)

- **REQ-018** (P0) When an interactive Claude Code session finishes a reply, the system
  speaks a summary of that reply.
- **REQ-019** (P0) Spoken summaries are short plain-language fact bullets that omit code,
  markup, and detail.
- **REQ-020** (P0) Claude CLI calls made by this system are marked, and the hook ignores
  marked calls, so the system never speaks its own output twice or summarises a summary.
- **REQ-021** (P0) The hook never blocks or delays Claude Code; it hands the text off and
  returns immediately, and a failure to reach the speech service is silent to the user.
- **REQ-022** (P1) Replies below a configured length are spoken directly, without the cost
  of a summarising model call.
- **REQ-023** (P2) The user can turn spoken summaries on or off without editing settings by
  hand.

### Text handling

- **REQ-024** (P0) Code blocks, markup symbols, URLs, and tables are removed from text
  before it is spoken.
- **REQ-025** (P0) Text arriving in fragments is buffered and processed with awareness of
  fragment boundaries, so markup and sentences spanning fragments are handled correctly.
- **REQ-026** (P1) Text is split into speakable chunks on sentence boundaries, with the
  first chunk released early to reduce time to first audio.

### Deferred to phase 2

- **REQ-027** (P2) A browser client provides the same conversation with true hold-to-talk
  while a key is held.
- **REQ-028** (P2) A hands-free mode detects when the user starts and stops speaking, with
  no key press.

## 6. Non-goals / out of scope

- No cloud speech services, and no paid service of any kind.
- No API-key authentication path; the subscription OAuth login is the only supported route.
- No wake word.
- No multi-user, multi-machine, or remote access; this runs for one user on one workstation.
- No mobile or web-hosted deployment.
- No speaker identification or voice cloning.
- No replacement for Claude Code's own `/voice` dictation inside its TUI. The two are
  complementary, not competing: `/voice` is input only and the hook is output only, so
  **`/voice` stays enabled** when using the hook. Disabling it is required only when running
  claudechat's own terminal client, which claims the spacebar for its push-to-talk.
- No GUI settings application in phase 1; configuration is a file.
- Phase 1 does not include the browser client or hands-free mode (REQ-027, REQ-028).

## 7. Constraints

- **Platform:** one Linux workstation, Wayland session, PipeWire 1.6.2 audio. Microphone is
  a USB device; playback is the onboard analogue output.
- **CPU only.** No GPU dependency, by explicit decision, even though a capable GPU is
  present.
- **Language:** Python, pinned to 3.13 via `uv`. Measured justification: 99.8 % of synthesis
  wall time is inside a native ONNX Runtime call and only 6 ms across the run is interpreter
  overhead, so a compiled language would not measurably improve throughput. Revisit only if
  a single distributable binary or lower audio jitter becomes a requirement.
- **Cost:** no paid dependencies or services. Model inference draws on the user's existing
  Claude subscription window.
- **Licensing:** permissive licences preferred. `kokoro-onnx` pulls `phonemizer` and
  `espeakng-loader`, both GPL-3.0, as hard dependencies. Accepted for a personal tool that
  is not distributed, since GPL obligations attach to conveying software rather than running
  it. This choice must be revisited before any public release.
- **Terminal input:** ordinary terminal emulators report key presses but not key releases,
  and this machine's terminal (VTE 0.84) advertises no enhanced keyboard protocol, so true
  hold-to-release capture may not be achievable in the terminal client.

## 8. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | Hook recursion: the system's own CLI calls fire the Stop hook, causing duplicated or looping speech. Confirmed to occur during design. | Mark internal calls with an environment variable and have the hook exit immediately when it is set. Verified during design that the marker reaches the hook process. |
| 2 | Interrupting fails to silence audio already queued in the playback buffer, so the user keeps hearing an abandoned reply. | Treat cancellation as: stop generating, discard queued chunks, and flush the audio device buffer. Test barge-in explicitly against the measured 300 ms target. |
| 3 | Killing a Claude turn leaves orphaned child processes, which accumulate and consume memory. | Start the CLI in its own process group and signal the whole group, escalating after a deadline. |
| 4 | Hold-to-talk proves impossible in the terminal, so the agreed interaction cannot be delivered as described. | Attempt key auto-repeat detection first; fall back to press-to-start / press-to-stop and state the difference plainly. True hold-to-talk is delivered by the phase 2 browser client. |
| 5 | Depending on an upstream package that is unmaintained or wrongly licensed. | Sentence chunking is written in-project rather than taking `stream2sentence`, which claims MIT in metadata but ships no LICENSE file. Licences of all adopted dependencies were verified by reading the repository LICENSE file during design. |
| 6 | Speech quality or latency proves unacceptable in real use despite good benchmark numbers. | Benchmarks are already recorded on this machine; re-measure against the metrics in section 4 with real speech before phase 1 is called done. |

## 9. Open questions

| # | Question | Owner | Blocking? |
|---|---|---|---|
| 1 | Can the terminal client detect key auto-repeat reliably enough for hold-to-talk, or does it fall back to press-to-start/stop? | agent | No — resolved by experiment during phase 1; fallback already agreed. |
| 2 | Does a persistent headless CLI process reduce time to first audio compared with starting one process per turn? | agent | No — an optimisation to measure after the engine works. |
| 3 | Which voice does the user prefer for everyday listening? | user | No — a configuration value; a default ships and is changed in the config file. |
| 4 | Should spoken summaries eventually be reworded by a local model rather than a Claude call, to cut cost further? | user | No — post-phase-1 consideration. |

Assumption: the summarising model call for REQ-018/REQ-019 uses the same Claude CLI path as
chat, subject to the same context-stripping as REQ-014. Recorded as an assumption because
the user has not been asked to confirm the cost of one extra short call per interactive
reply.

## 10. Readiness gate

- [x] Every P0 requirement is testable as written
- [x] Success metrics have numeric targets
- [x] Non-goals section is non-empty
- [x] No open question is marked blocking
- [ ] WAIVED — user has not yet confirmed the REQ list line by line. The design, phasing,
      CPU-only constraint, and language choice were each confirmed in conversation, but the
      numbered requirements above have not been read back to the user. This waiver is
      visible, not silent.

Verdict: READY
