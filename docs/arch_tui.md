# Architecture: TUI

This document describes `silc/tui/` and the CLI TUI launch flow.

## Overview

SILC currently has two TUI paths:

1. **Native TUI** — the primary path launched by `silc tui`
2. **Textual TUI** — legacy Python app launched by deprecated `silc open`

## Scope Boundary

Owns:

- native TUI binary discovery and installation
- TUI launch wiring from the CLI
- legacy Textual app implementation

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

The Rust client ignores websocket ping/pong frames, reports close code/reason on disconnect, and strips terminal device-attribute query noise from rendered output.

## Legacy Textual TUI

`silc open` is deprecated and still launches `launch_tui(port)` from `silc/tui/app.py`.

That app is a legacy websocket client that:

- connects to the per-session websocket
- renders output in Textual
- sends keyboard input from the terminal

It still speaks the older JSON websocket shape in `app.py`, so treat it as stale compatibility code relative to the current binary frame protocol.

It remains in the repo for backwards compatibility, but it is not the primary TUI path.

## Error Handling

- If the native binary cannot be resolved, the CLI prints a manual-install hint.
- If `pywebview` is missing, desktop launch fails with a clear error.
- Legacy websocket disconnects simply end the app.
