# claudechat

`claudechat` is a local, CPU-only voice interface for Claude on one Linux workstation. It
records a question, transcribes it locally, asks Claude through the logged-in Claude Code CLI,
and speaks the streamed reply. It can also announce short summaries of replies from interactive
Claude Code sessions.

It uses no API key, cloud speech service, GPU, or CUDA. Claude access reuses the existing Claude
Code OAuth login.

## Install and run

Install the pinned Python dependencies and launch the terminal client:

```bash
uv sync
uv run claudechat
```

The terminal client currently uses toggle input: press Enter to begin recording and Enter again
to stop; Ctrl-C exits cleanly. Disable Claude Code's built-in `/voice` feature separately to free
the keybinding it uses.

## Spoken Claude Code summaries

Register the Stop hook once:

```bash
uv run python scripts/install_hook.py
```

Enable summaries in `~/.config/claudechat/config.toml`:

```toml
[hook]
spoken_summaries = true
summary_threshold_chars = 400
```

Keep `claudechat` running so its local engine service can receive hook announcements. The hook
is intentionally silent and non-blocking when that service is not running. Internal calls made
by claudechat are marked so they are never announced a second time or summarised recursively.

## Performance check

Run the local benchmark to report speech and first-audio timings against the PRD targets:

```bash
uv run python scripts/benchmark.py
```

See [the PRD](docs/PRD.md) for requirements and success metrics, and [the architecture decision
records](docs/adr) for the decisions behind the implementation.
