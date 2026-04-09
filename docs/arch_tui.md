# Architecture: TUI

This document describes the native TUI and the CLI TUI launch flow.

## Overview

SILC currently has one runtime TUI path:

1. **Native TUI** — the primary path launched by `silc tui`

`silc pick` is a separate Python console selector. It does not render the runtime terminal; it only chooses an existing session or creates a new one before handing off to the native TUI.

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

The bootstrap flows are now split:

1. `scripts/install.sh` / `scripts/install.ps1` are the default remote bootstrap scripts. They are intended to be run directly from GitHub raw URLs, download a prebuilt repo-mirror zip from Releases, unpack it, and run `uv tool install --force --editable <folder>`.
2. `scripts/install-source.sh` / `scripts/install-source.ps1` are the guided source-bootstrap scripts. They are also intended to be runnable from GitHub raw URLs, prepare a source tree, build the web UI in place, place the matching `silc-tui-*` asset into `tui_client/dist/`, and then run `uv tool install --force --editable <folder>`.
3. Manual developer installs may clone the repo and prepare the same layout by hand.

`ensure_native_tui_binary()` is now a local resolver only. It never downloads anything and never reads user-global cache directories.

The resolver only looks for local `silc-tui` / `silc-tui.exe` binaries in these in-tree locations:

- `tui_client/dist/` inside the active editable-install tree
- `tui_client/dist/` inside a local source checkout

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

The Rust client ignores websocket ping/pong frames, reports close code/reason on disconnect, and feeds PTY bytes through `par-term-emu-core-rust` so terminal negotiation is parsed instead of rendered. Rendering repaints dirty rows cell-by-cell with explicit foreground/background painting, and resize paths force a full refresh.

## Error Handling

- If the native binary cannot be resolved, the CLI tells the user to rerun the installer script or restore the binary inside the installed SILC tree.
- If `pywebview` is missing, desktop launch fails with a clear error.
