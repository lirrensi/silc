# Architecture: TUI

This document describes the native TUI and the CLI TUI launch flow.

## Overview

SILC currently has one TUI path:

1. **Native TUI** — the primary path launched by `silc tui`

## Scope Boundary

Owns:

- native TUI binary discovery and installation
- TUI launch wiring from the CLI


Does not own:

- session PTY behavior (`silc/core/`)
- websocket protocol implementation (`silc/api/server.py`)
- daemon lifecycle (`silc/daemon/`)

## Native TUI

### Installer

`ensure_native_tui_binary()` resolves the bundled binary first, then falls back to a cached or downloaded release binary when SILC is running from source.

Environment variables:

| Variable | Purpose |
|---|---|
| `SILC_TUI_BIN_DIR` | Override install cache directory |
| `SILC_TUI_RELEASE_REPO` | Override release repo (`owner/repo`) |
| `SILC_TUI_RELEASE_API` | Override release API URL |

Default repo/API:

- `lirrensi/silc`
- `https://api.github.com/repos/lirrensi/silc/releases/latest`

The fallback installer selects an asset by platform + architecture keywords, extracts or copies `silc-tui` / `silc-tui.exe`, and marks it executable.

### Launching

`silc tui`:

- resolves the binary
- checks session status and asks before taking over an active interactive client
- prints the websocket URL
- launches the binary with `ws://127.0.0.1:<port>/ws`

The websocket endpoint accepts token query params for remote use; the local CLI launcher itself passes a plain localhost websocket URL.

## Websocket Protocol

The native TUI uses the same binary envelope as the session websocket:

```text
[4-byte big-endian header length][JSON header UTF-8 bytes][raw payload bytes]
```

Server messages include `output`, `history`, `title`, and `cwd`.
Client messages include `input` and `load_history`.

The Rust client ignores websocket ping/pong frames, reports close code/reason on disconnect, and feeds PTY bytes through `par-term-emu-core-rust` so terminal negotiation is parsed instead of rendered. Rendering repaints dirty rows cell-by-cell with explicit foreground/background painting, and resize/reset paths force a full refresh.

## Error Handling

- If the native binary cannot be resolved, the CLI prints a manual-install hint.
- If `pywebview` is missing, desktop launch fails with a clear error.
