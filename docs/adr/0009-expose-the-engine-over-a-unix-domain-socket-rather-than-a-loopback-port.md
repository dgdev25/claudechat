# 0009 — Expose the engine over a Unix domain socket rather than a loopback port

## Status

Accepted (2026-08-22)

## Context

The Claude Code hook must hand reply text to the running engine. The obvious choice is an HTTP
server on a loopback port. Two independent security reviews rejected that. A loopback port is
reachable by every process on the machine, and a web page can reach one through DNS rebinding.
This endpoint is not merely a speaker: it spends the users Claude subscription quota by
triggering a summarising model call, and it makes the machines speakers talk.

## Decision

Expose one Unix domain socket at `$XDG_RUNTIME_DIR/claudechat/engine.sock`, with the directory
at mode `0700` and the socket at `0600`. Verify the connecting peers UID with `SO_PEERCRED`
and reject any other UID. Expose exactly one operation — speak a hook reply — with a
size-capped body and a strict schema. Never open a TCP listener.

## Consequences

Good: filesystem permissions and a peer UID check exclude other local users, and no network
listener exists at all, so remote and browser-based attacks do not apply. The narrow operation
means a caller cannot choose a model, a command, or an audio device.

Bad: a browser cannot speak to a Unix socket, so phase 2 needs a bridge or a separate loopback
listener for the browser client — at which point the remote attack surface returns and must be
threat-modelled again. Code running as this same user is not excluded by any of this, which
the design states rather than implying otherwise.

## Alternatives

- Loopback HTTP port — rejected: reachable by any local process and by browser pages via DNS
  rebinding, on an endpoint that spends money and produces sound.
- A named pipe — rejected: no peer credential check is available, and the request/response
  shape is more awkward.
- A watched file or directory — rejected: racy, leaves reply text on disk, and gives no way to
  authenticate the writer.
