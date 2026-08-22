# 0002 — Strip project context, tools, and MCP from every voice turn

## Status

Accepted (2026-08-22)

## Context

Headless CLI runs inherit the working directory context: CLAUDE.md, every skill, every MCP
server, and all built-in tool definitions. Measured on this machine, a trivial prompt in a
normal project directory cost 32,534 cache-creation tokens. The same prompt with MCP servers,
plugins, skills, and tools disabled cost 3,489 tokens — a ninefold reduction. Voice turns are
frequent and short, so per-turn context dominates total consumption of the users five-hour
subscription window.

## Decision

Every voice turn runs with `--strict-mcp-config --mcp-config {"mcpServers":{}}`, `--tools ""`,
`--disable-slash-commands`, `--exclude-dynamic-system-prompt-sections`, an explicit short
`--system-prompt`, and plugins disabled. These flags are mandatory, not tuning.

## Consequences

Good: roughly nine times more conversation within the same subscription window; lower
latency; and, because no tools are available, a successful prompt injection cannot take
action on the machine.

Bad: the voice assistant cannot read files, run commands, or use MCP servers. It converses
but cannot act. Any future "do this task by voice" feature needs a separate, deliberately
scoped mode with its own security review.

## Alternatives

- Inherit normal project context — rejected: nine times the token cost per turn and it gives
  the model tools it does not need for conversation.
- Use `--bare` to skip hooks and plugins — rejected: bare mode requires an API key and cannot
  use the OAuth login.
