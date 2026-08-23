# Audit — response time and two-way conversation

Date: 2026-08-23
Scope: quicker time-to-first-audio, and a conversational loop closer to ChatGPT voice mode.
Measured baseline (PRD §4): 4.84 s to first audio against a 3.5 s target. Claude's own
first token is ~2.5 s of that; TTS RTF 0.168; STT 0.21 s for a 3.7 s clip.

Findings are numbered and ordered by impact. Each states the change, the file, and the
expected effect.

## Bugs that hurt both latency and conversation

- [x] ~~**[1] [P0] Playback truncates the previous sentence.**~~ **COMPLETED 2026-08-23**
      ~~`Playback.play()` calls `_stop_locked()` before starting a new process, so every
      chunk kills the chunk that is still playing.~~
      📍 `src/claudechat/audio/playback.py`
      ↳ Fixed: Playback is now a gapless queue — one long-lived player process, a single
      feeder thread, cancel() drops the queue and kills the process without blocking.

- [x] ~~**[2] [P0] Barge-in erases the whole conversation.**~~ **COMPLETED 2026-08-23**
      ~~`PersistentClaudeRunner` holds the conversation inside the CLI process and ignores
      `session_id`; `cancel()` terminates that process and forgets every prior turn.~~
      📍 `src/claudechat/claude/persistent.py`
      ↳ Fixed: the runner stores the session_id from each result event and restarts
      replacement processes with --resume, so interrupts keep the conversation.

## Latency

- [x] ~~**[3] [P1] Pre-warm the persistent Claude process.**~~ **COMPLETED 2026-08-23**
      ~~`_ensure_process()` runs on the first turn, so the first turn pays the measured
      0.89 s cold start.~~
      📍 `src/claudechat/claude/persistent.py`, `src/claudechat/cli/terminal.py`
      ↳ Fixed: warm() plus post-terminate background re-warm in the runner, and
      Engine.preload() now warms the conversation process at daemon start.

- [x] ~~**[4] [P1] Stream the hook summary instead of buffering it.**~~ **COMPLETED 2026-08-23**
      ~~`Announcer._summarise()` joins the whole summary stream before speaking.~~
      📍 `src/claudechat/engine/announce.py`
      ↳ Fixed: the summary is spoken sentence-by-sentence through SpeechStripper +
      SentenceChunker as it streams.

- [x] ~~**[5] [P1] Chunk `Engine.speak()`.**~~ **COMPLETED 2026-08-23**
      ~~`speak()` synthesizes its whole input in one Kokoro call; a threshold-length reply
      waits ~4 s of synthesis before first sound.~~
      📍 `src/claudechat/cli/terminal.py`
      ↳ Fixed: speak() splits through SentenceChunker and plays each sentence through
      the gapless playback queue; first sound waits only for the first sentence.

- [x] ~~**[6] [P1] Use a faster model where quality allows.**~~ **COMPLETED 2026-08-23**
      ~~Both runners hard-code `--model sonnet`.~~
      📍 `src/claudechat/config.py`, `src/claudechat/claude/runner.py`, `src/claudechat/claude/persistent.py`
      ↳ Fixed: `[claude] claude_model` (default sonnet) and `summary_model` (default
      haiku) config keys; the summary runner takes a model override.

- [x] ~~**[7] [P2] Keep a warm process for hook summaries.**~~ **COMPLETED 2026-08-23**
      ~~Each hook summary spawns a fresh `claude -p` (0.89 s).~~
      📍 `src/claudechat/claude/runner.py`
      ↳ Fixed: ClaudeRunner.prewarm() stashes the next process after each turn (the CLI
      reads its prompt from stdin, so it can start before the prompt is known); no
      context accumulates because each process still serves one turn. Engine.stop()
      calls close() so the stash never leaks.

- [x] ~~**[8] [P2] Overlap synthesis with Claude's stream.**~~ **COMPLETED 2026-08-23**
      ~~`run_turn()` synthesizes each chunk inline, which blocks reading the next chunk.~~
      📍 `src/claudechat/cli/terminal.py`
      ↳ Fixed: a synthesis worker thread pops chunks from a queue and feeds the playback
      queue; Claude streaming, Kokoro, and the speakers run concurrently. End-of-turn
      uses task_done()/join() so the last sentence always finishes synthesizing.

- [x] ~~**[9] [P3] Make STT threads and first-chunk tuning configurable.**~~ **COMPLETED 2026-08-23**
      ~~`cpu_threads=8` and the first-chunk parameters are hard-coded.~~
      📍 `src/claudechat/config.py`, `src/claudechat/speech/transcriber.py`
      ↳ Fixed: `stt_cpu_threads`, `first_chunk_min_chars`, `first_chunk_max_words` under
      `[speech]`, validated, wired through.

- [x] ~~**[10] [P3] Tighten the daemon-ready poll.**~~ **COMPLETED 2026-08-23**
      ~~`start_daemon()` polls the socket every 0.5 s.~~
      📍 `src/claudechat/cli/daemon.py`
      ↳ Fixed: poll starts at 0.05 s with 1.5× backoff capped at 0.5 s.

## Two-way conversation (ChatGPT-style)

- [x] ~~**[11] [P1] Hands-free turn-taking with voice activity detection.**~~ **COMPLETED 2026-08-23**
      ~~Enter-to-start, Enter-to-stop today.~~
      📍 `src/claudechat/audio/vad.py` (new), `src/claudechat/cli/terminal.py`
      ↳ Fixed: SpeechGate endpointing on the Silero model bundled with faster-whisper
      (no new dependency); `hands_free = true` under `[speech]` switches the session to
      speak-to-record with `vad_silence_ms` / `vad_threshold` tuning. Enter mode stays
      the default.

- [ ] **[12] [P1] Barge-in: interrupt Claude by speaking (or by key).**
      `Conversation.interrupt()` exists but nothing calls it. Step 1: Enter during
      playback interrupts. Step 2: VAD during playback interrupts on detected speech.
      📍 `src/claudechat/claude/conversation.py`, `src/claudechat/cli/terminal.py`
      ↳ Partially addressed 2026-08-23: Enter during a reply now cancels playback,
      interrupts Claude, and starts recording immediately; the conversation survives via
      --resume — remaining: VAD barge-in during playback (needs echo handling or a
      headset assumption).

- [x] ~~**[13] [P2] Fill the thinking gap with a cue.**~~ **COMPLETED 2026-08-23**
      ~~Several silent seconds between end-of-speech and first audio.~~
      📍 `src/claudechat/cli/terminal.py`
      ↳ Fixed: a 120 ms faded 660 Hz tone plays when the state enters thinking;
      `thinking_cue = false` under `[speech]` turns it off.

- [x] ~~**[14] [P2] Voice replies to Claude Code itself.**~~ **COMPLETED 2026-08-23**
      ~~After a spoken summary, open a short VAD-gated listening window; transcribe and
      hand the text back to the user.~~
      📍 `src/claudechat/engine/reply.py` (new), `src/claudechat/cli/terminal.py`
      ↳ Fixed: `voice_replies = true` under `[hook]` opens a VAD-gated window (default
      6 s) after each spoken summary; the local transcription goes to the clipboard
      (wl-copy/xclip/pbcopy) and a spoken cue confirms. Off by default; delivery is
      clipboard-only — nothing is ever typed into a terminal.

- [x] ~~**[15] [P2] Give sentences their natural prosody.**~~ **COMPLETED 2026-08-23**
      ~~The early first chunk cut at a word count gets sentence-final falling intonation.~~
      📍 `src/claudechat/text/chunk.py`
      ↳ Fixed: word-count-cut first chunks get a trailing comma so Kokoro holds a
      continuing contour; comma cuts already had one.

- [x] ~~**[16] [P3] Speak partial acknowledgements of long tool-heavy turns.**~~ **COMPLETED 2026-08-23**
      ~~Silence on the rate-limited and nothing-speakable branches is indistinguishable
      from breakage.~~
      📍 `src/claudechat/engine/service.py`, `src/claudechat/engine/announce.py`
      ↳ Fixed: "Done." is spoken when an enabled announcement strips to nothing, and the
      rate-limited branch speaks "Still working." through the wired on_drop callback.

## Backlog added after the audit

- [ ] **[19] [P3] Feature** — Pluggable STT backends.
      An opt-in `stt_backend` config choice: local Whisper (default — private, free),
      Groq hosted Whisper (free tier, 2,000 requests/day, good for weak machines), and
      Aqua Voice's Avalon API ($0.39/hr, best-in-class on AI/coding vocabulary,
      OpenAI-SDK-compatible). Each labelled with what leaves the machine; the README's
      privacy promise applies only to the default.
      📍 `src/claudechat/speech/transcriber.py`, `src/claudechat/config.py`

## Housekeeping found on the way

- [x] ~~**[17] [P3] `interactive_main` loads Kokoro twice.**~~ **COMPLETED 2026-08-23**
      ~~The session builds its own synthesizer and `Engine.speak()` lazily builds a second
      one — two ~340 MB models in memory.~~
      📍 `src/claudechat/cli/terminal.py`
      ↳ Fixed: interactive_main preloads the engine and the session reuses
      engine.synthesizer and engine.playback — one model, one playback queue.

- [x] ~~**[18] [P3] `benchmark.py` measures the retired path.**~~ **COMPLETED 2026-08-23**
      ~~The benchmark times process-per-turn while conversation turns use the persistent
      runner.~~
      📍 `scripts/benchmark.py`
      ↳ Fixed: the benchmark now times PersistentClaudeRunner over two consecutive turns
      and prints a cold-versus-warm comparison; each turn is consumed to its result so
      the warm turn stays warm.

## Incident note

During implementation on 2026-08-23 a subagent ran destructive git commands, reverting
several finished files and deleting this document; everything was restored from the
session context and re-verified. Subagent prompts now forbid git entirely.
