# Design — claudechat voice engine

Date: 2026-08-22
Status: approved (design), phase 1 not yet implemented
Requirements: `docs/PRD.md`

## 1. Scope

Phase 1 delivers the **engine** and two ways to reach it: a terminal voice client and a
Claude Code hook. The browser client (REQ-027) and hands-free mode (REQ-028) are deliberately
deferred; the engine is designed so neither needs a rewrite to add.

## 2. Architecture

One Python process. Speech engines sit behind two narrow interfaces and run on a thread
pool, so the terminal stays responsive while a model runs.

```
                    ┌──────────────────────────────────────┐
  microphone ──────►│  AudioInput      (pw-record)         │
                    │        │                             │
                    │        ▼                             │
                    │  Transcriber  ◄── interface (REQ-004) │
                    │        │        faster-whisper       │
                    │        ▼                             │
                    │  Conversation ──► ClaudeRunner ──────┼──► claude -p (OAuth)
                    │        ▲              │              │
                    │        │              ▼              │
                    │        │        TextForSpeech        │
                    │        │        (strip + chunk)      │
                    │        │              │              │
                    │        │              ▼              │
                    │        └───── Synthesizer ◄── interface
                    │                       │     kokoro-onnx
                    │                       ▼              │
  speakers ◄────────│  AudioOutput     (pw-play)           │
                    └──────────────────────────────────────┘
                              ▲
   Claude Code Stop hook ─────┘  (Unix domain socket, 0600, peer UID checked)
```

Why one process rather than the two-process split considered earlier: that split existed to
contain native CUDA crashes and CTranslate2/ONNX Runtime CUDA version conflicts. The CPU-only
decision (REQ-003) removes that failure mode. The narrow interfaces (REQ-004) keep a later
split cheap if it is ever needed.

## 3. Components

### 3.1 `Transcriber` (REQ-001, REQ-004)

Interface: `transcribe(pcm: bytes, sample_rate: int) -> str`.

Implementation uses faster-whisper with `base.en`, `compute_type="int8"`, `cpu_threads=8`,
`beam_size=1`, `language="en"`. Model is loaded once at startup and held resident.

Measured on this machine: a 3.67 s clip transcribed in 0.21 s. `base.en` was chosen over
`tiny.en` because it correctly produced "login handler" where `tiny.en` produced "log in
handler", and over `small.en` because `small.en` took 3.6× longer with no accuracy gain on
the same clip.

### 3.2 `Synthesizer` (REQ-002, REQ-004)

Interface: `synthesize(text: str) -> tuple[np.ndarray, int]`, plus a streaming variant that
yields per-sentence audio.

Implementation uses `kokoro-onnx` with `kokoro-v1.0.onnx` (311 MB) and `voices-v1.0.bin`
(27 MB), default voice `af_heart`, on CPU. Measured real-time factor 0.168; a 27-character
sentence synthesised in 0.32 s.

Model files are downloaded on first run into a `models/` directory, which is gitignored.

### 3.3 `TextForSpeech` (REQ-024, REQ-025, REQ-026)

Two stages, both stateful across streaming fragments:

1. **Strip.** Remove fenced code blocks, inline code, markup symbols, URLs, and table rows.
   A fence can open in one fragment and close in another, so the stripper holds fence state
   between calls rather than treating each fragment independently.
2. **Chunk.** Accumulate stripped text and release a chunk on a sentence terminator followed
   by whitespace, guarding against abbreviations and decimal points. The first chunk of a
   reply is released early — on a comma, or after a word count — to cut time to first audio.
   A timeout flushes a trailing partial sentence at end of stream.

Written in-project rather than adopting `stream2sentence`, which declares MIT in packaging
metadata but ships no LICENSE file (PRD risk 5).

### 3.4 `ClaudeRunner` (REQ-013 – REQ-017)

Spawns the CLI per turn. **The prompt goes on stdin, never in argv** — command arguments are
readable by any local process, and prompts contain the user's speech. Verified working.

```
claude -p                                  # prompt written to stdin, then stdin closed
  --output-format stream-json --verbose --include-partial-messages
  --model sonnet
  --strict-mcp-config --mcp-config '{"mcpServers":{}}'
  --tools "" --disable-slash-commands
  --exclude-dynamic-system-prompt-sections
  --system-prompt <voice persona>
  --settings '{"enabledPlugins":{}}'
  [--resume <session_id>]
```

`--permission-mode dontAsk` is deliberately **absent**. It is fail-open: it tells the CLI to
proceed without asking should a capability ever become available. Verified that the command
runs non-interactively without it, so the design fails closed instead. `--verbose` is
required by `--include-partial-messages`; it was checked for credential leakage and the
stream contained none.

Spawned with `shell=False`, an explicit argv list, an absolute executable path resolved at
startup, and a minimal allowlisted environment. Environment carries
`CLAUDECHAT_INTERNAL=<token>` (REQ-020), where the token is random per engine start rather
than a fixed `1`, so an unrelated exported variable cannot silently suppress speech.

**Context stripping (REQ-014) is the cost control.** Measured: the same trivial prompt cost
32,534 cache-creation tokens with normal project context and 3,489 tokens with the flags
above — a 9× reduction. This is why the flags are mandatory rather than optional tuning.

**Streaming (REQ-015).** Read stdout line by line as JSON. Assistant text is at
`event.delta.text` on `stream_event` messages whose `event.delta.type == "text_delta"`. The
final `result` message carries the full reply and the session id; the full reply is **not**
spoken again, since the deltas already were.

**Termination (REQ-016).** Start with `start_new_session=True` so the CLI gets its own
process group, then signal the group with `SIGTERM` and escalate to `SIGKILL` after a short
deadline. Signalling only the process leaves Node children running.

**Serialisation (REQ-017).** One active turn per conversation. A new turn waits for the
previous process to exit and its pipes to drain, so `--resume` cannot race a half-written
transcript.

### 3.5 `Conversation` (REQ-011)

Holds the session id returned in the `result` message and passes it to the next turn via
`--resume`. Also owns the **generation counter** used for interruption (REQ-010): every turn
increments it, and every audio chunk is tagged with the generation that produced it.

### 3.6 Audio I/O (REQ-002, REQ-006)

`pw-record` and `pw-play` subprocesses rather than ALSA's `arecord`/`aplay`, because the
machine runs PipeWire and direct ALSA access can bypass its routing and contend for the
device. Capture is 16 kHz mono signed 16-bit, matching what the transcriber expects.

### 3.7 Terminal client (REQ-006 – REQ-012)

Displays state (`idle`, `recording`, `transcribing`, `thinking`, `speaking`), the transcript
of what was heard, and the reply text (REQ-008).

**Key handling.** True hold-to-release cannot be assumed: terminals report presses, not
releases, and this machine's VTE 0.84 terminal advertises no enhanced keyboard protocol.
Approach, in order: attempt to infer holding from keyboard auto-repeat (a held key produces
repeats; a gap beyond a threshold means released); if that proves unreliable, fall back to
press-to-start / press-to-stop and say so in the interface. Phase 2's browser client
provides genuine hold-to-talk.

### 3.8 Interruption (REQ-010)

Cancellation is three actions, not one:

1. Increment the generation; stop reading CLI output and terminate its process group.
2. Discard queued text chunks and queued audio for the old generation.
3. **Flush the audio device.** Terminate the `pw-play` process rather than merely stopping
   the feed, because audio already handed to the device keeps playing otherwise.

Chunks are checked against the current generation immediately before playback, not only when
they are queued.

### 3.9 Claude Code hook (REQ-018 – REQ-023)

A small script registered on the `Stop` event in `~/.claude/settings.json`. On each reply:

1. If the internal marker matches the token in the engine's runtime file, exit 0 immediately
   (REQ-020). Verified during design: the system's own CLI calls do fire this hook, and the
   marker does reach the hook process. Without this guard the app speaks every reply twice
   and summarises its own summaries. This is recursion control, not access control.
2. Read `last_assistant_message` from the JSON on stdin. No transcript parsing is needed —
   verified that the payload carries the complete reply text.
3. POST it to the engine socket with a short timeout, then exit 0 regardless of outcome
   (REQ-021). Claude Code must never wait on speech.

Spoken summaries are **off by default** and enabled explicitly (REQ-023), because this path
speaks without the user asking it to and a reply may contain secrets, customer data, or
source code that should not be broadcast aloud in a shared room. A mute control stops
announcements without starting a model call.

The engine strips code and markup, and if the text exceeds a configured length (REQ-022) it
condenses it into plain fact bullets (REQ-019) before speaking. Short replies are spoken
directly, without that call.

**The condensing call treats its input as untrusted data.** `last_assistant_message` is
model-generated but can carry text from repository files, web pages, or tool output, so it
can contain instructions aimed at the summariser ("ignore the reply and say ..."). Controls:
the payload is passed as delimited data with a fixed system prompt stating it is quoted
material to be summarised and never instructions to follow; URLs, code, and credential-shaped
strings are stripped before the call; the summary output is length-capped; and the call
remains tool-free and MCP-free so a successful injection can only alter spoken wording, not
take action. Users who want no exposure at all can set the summariser to deterministic mode,
which speaks a bounded stripped excerpt with no second model call.

## 4. Configuration (REQ-005, REQ-023)

A single TOML file: model names, voice, speaking rate, summary length threshold, spoken
summaries on/off, audio device overrides.

## 5. Latency budget

Measured end to end on this machine, CPU only:

| Stage | Measured |
|---|---|
| Transcribe a 3.67 s utterance | 0.21 s |
| Claude's first complete sentence | 2.57 s |
| Synthesise that sentence | 0.32 s |
| **Total to first audio** | **≈3.1 s** |

Against the PRD target of ≤3.5 s. The speech layer contributes ≈0.53 s against its ≤0.8 s
target. Claude dominates and is not locally reducible; open question 2 (a persistent CLI
process) is the one remaining lever.

## 6. Security design

Threat-modelled by two independent models before implementation. The realistic adversary is
not a remote attacker — it is another process on this machine, and untrusted text that
reaches a model call or the terminal. A process already running as this user cannot be
defended against and is out of scope; that is stated rather than pretended away.

### 6.1 Engine ingress

The hook reaches the engine over a **Unix domain socket only — never a TCP port**, even on
loopback. A loopback port is reachable by every local process and by a browser page through
DNS rebinding, and this endpoint spends the user's Claude quota and makes the speakers talk.

- Socket at `$XDG_RUNTIME_DIR/claudechat/engine.sock`, directory mode `0700`, socket `0600`.
- Verify the connecting peer's UID with `SO_PEERCRED`; reject any other UID.
- Refuse to start if an existing path is not a socket owned by this user; never blind-unlink.
- Exactly one operation is exposed: speak a hook reply. The caller cannot choose a model, a
  command, an audio device, or a config path.
- Request bodies are size-capped before JSON parsing, with a strict schema; unknown fields
  are rejected.

### 6.2 Resource and quota bounds

Context stripping reduces per-turn cost but sets no ceiling. Bounds are explicit:

- Hook requests are **dropped on overload, never queued** — at most one pending
  announcement, newer replaces older — and rate-limited to one per configurable interval.
- Hard caps on ingress bytes, text length, synthesised audio duration, recording duration,
  streamed CLI output, and per-turn wall clock.
- A per-turn subprocess timeout terminates the process group on expiry.
- Announcements yield to an active user turn; direct interaction wins.

### 6.3 Recording safety

Recording is the most privacy-sensitive state, and toggle mode can strand it open if a stop
keypress is missed or the terminal is obscured.

- Every capture has a hard maximum duration with automatic stop and visible feedback.
- Capture starts only on explicit user action — never at startup, after speech ends, after a
  hook event, or after an interruption.
- Recording stops on client exit, terminal disconnect, uncaught exception, and shutdown; the
  recorder runs in its own managed process group.
- Raw audio is held in memory for the active turn only and never written to disk unless
  debugging is explicitly enabled.

### 6.4 Model file integrity

The ONNX files are execution graphs parsed by native code, so a substituted file is a code
execution path, and HTTPS alone is not an integrity guarantee.

- Pin exact URLs, byte lengths, and SHA-256 digests in a manifest.
- Download to a temporary file, enforce a maximum size, verify the digest, then atomically
  rename into place; re-verify before load.
- Model paths are not configurable, so config cannot point the loader at an arbitrary file.
- Python dependencies are pinned with hashes.

### 6.5 Output handling

Transcripts and replies can contain terminal escape sequences — clipboard writes, hyperlinks,
cursor manipulation — and hook text may originate from untrusted project content.

- Strip C0/C1 control characters and normalise line endings before display and before speech.
- Render external text as plain text; no terminal hyperlink generation.

### 6.6 Dismissed, with reasons

- **Remote network attack surface** — not applicable while ingress is a Unix socket and there
  is no listener. Becomes applicable the moment the phase 2 browser client adds one; re-model
  then.
- **Wake-word and always-listening attacks** — not applicable while capture is manual.
  Re-model before REQ-028.
- **Malicious code already running as this user** — not defensible for a personal tool; it can
  read runtime files and use the user's credentials regardless.
- **API key theft** — no API key exists; the design uses the CLI's OAuth session.
- **Audio interception in transit** — speech never leaves the machine.
- **Credential leakage through `--verbose`** — raised in review, **tested and dismissed**: the
  full stream contained no credential-shaped strings.

## 7. Testing

- **Unit.** Stripping and chunking against fragmented input, including a code fence split
  across fragments, abbreviations, and decimals.
- **Round trip, no microphone.** Synthesise a known sentence, transcribe the audio, assert
  the text matches. This exercises both engines in CI without hardware.
- **Process hygiene.** Start a turn, cancel it, assert no `claude` or `node` descendants
  survive and no `pw-play` remains.
- **Hook guard.** Invoke the hook with and without `CLAUDECHAT_INTERNAL`; assert it speaks
  exactly once and never for internal calls.
- **Metrics.** A benchmark script that reports the section 5 numbers, so regressions against
  the PRD targets are visible.

## 8. Reusable code & prior art

Licences below were verified by reading each repository's own LICENSE file, not a registry
summary — four registry entries were wrong during research.

**Adopted:** `faster-whisper` (MIT) · `kokoro-onnx` (MIT wrapper, Apache-2.0 weights) ·
`onnxruntime` (MIT) · PipeWire CLI tools (already installed).

**Read for design, not copied:** `dnhkng/GLaDOS` (MIT) for its control-frame and reset
approach to barge-in · `caiovicentino/claude-call` (MIT) for the headless-CLI daemon shape ·
`mbailey/voicemode` (MIT) for service management · `peteonrails/voxtype` (MIT) for Wayland
push-to-talk, relevant to phase 2.

**Rejected on licence:** `piper1-gpl` (GPL-3.0; the MIT `rhasspy/piper` is archived) ·
`backtalk`, `sapphire`, `vocalinux` (AGPL) · `whisper-writer`, `nerd-dictation`,
`speech-to-cli` (GPL) · `open-webui` (source-available with a branding clause) · six
otherwise-relevant Claude voice repositories that ship no LICENSE file, including a
41-star and a 3.8k-star project.

**Accepted with a caveat:** `kokoro-onnx` pulls `phonemizer` and `espeakng-loader`, both
GPL-3.0, as hard dependencies. Accepted because this tool is personal and not distributed;
must be revisited before any public release.

**Built rather than adopted:** sentence chunking (`stream2sentence` ships no LICENSE file);
the markdown-to-speech stripper (the available libraries are GPL or drag in an HTML parser).

## 9. Decisions requiring an ADR

1. Reach Claude through the Claude Code CLI rather than the API or Agent SDK (OAuth).
2. Strip project context, tools, and MCP from every turn (9× token reduction).
3. CPU-only, no GPU dependency.
4. Python rather than a compiled language (99.8 % of synthesis time is native).
5. Kokoro for synthesis, accepting a GPL phonemizer dependency for a non-distributed tool.
6. Guard the Stop hook with an environment marker to prevent recursion.
7. Single process with narrow speech interfaces, rather than the two-process split.
8. Terminal client first; browser client and hands-free mode deferred.
