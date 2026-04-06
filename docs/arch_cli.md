# Architecture: CLI

This document describes `silc/__main__.py`.

## Overview

The CLI is a Click-based front end for:

- starting or managing the daemon
- operating on an existing session by port or name
- launching the manager UI, desktop webview, TUI, and MCP server
- installing OS integrations

## Scope Boundary

Owns:

- command parsing and validation
- daemon/session HTTP client behavior
- user-facing output and warnings
- native TUI launch/install flow

Does not own:

- daemon runtime logic (`silc/daemon/`)
- session behavior (`silc/core/`)
- session API behavior (`silc/api/server.py`)

## Command Tree

```text
silc
├── start [name] [--port] [--global] [--no-detach] [--token] [--shell] [--cwd]
├── start-enter [name] [--port] [--global] [--no-detach] [--token] [--shell] [--cwd]
├── manager [--share]
├── desktop [--share]
├── mcp
├── list
├── shutdown
├── killall
├── restart-server
├── resurrect
├── restart
├── logs [--tail]
├── os-integration install|uninstall
├── daemon (hidden)
├── desktop-window (hidden)
├── open (deprecated session command)
└── <port|name>
    ├── run <command...> [--timeout]
    ├── out [lines]
    ├── in <text...>
    ├── status
    ├── interrupt
    ├── clear
    ├── reset
    ├── resize <rows> <cols>
    ├── close
    ├── kill
    ├── restart
    ├── logs [--tail]
    ├── tui
    ├── web
    ├── stream-file-render
    ├── stream-file-append
    ├── stream-stop
    └── stream-status
```

## Session Target Resolution

- A session selector may be a **port** or a **name**.
- Numeric selectors become `port`-bound groups.
- Valid names are resolved through the daemon (`GET /resolve/{name}`).
- Invalid names are rejected before any request is sent.

## `silc start`

Behavior:

1. Validate an explicit name if provided.
2. Generate a token for `--global` if one is not supplied.
3. Warn loudly about network exposure when using `--global` or `--share`.
4. Start or reuse the daemon.
5. If no name is provided, derive one from the current folder name.
6. Create the session through the daemon API.
7. Print connection hints for TUI, web UI, and API access.

Notes:

- Folder-derived names are sanitized and collision-safe (`name`, `name-2`, ...).
- `--no-detach` starts the daemon in-process instead of detaching.
- `--global` is a session-level network exposure mode, distinct from daemon `--share`.

## `silc start-enter`

Behavior:

1. Runs the same start flow as `silc start`.
2. Launches the native TUI immediately against the created session port.

Notes:

- It uses the same session options as `silc start`.
- `--no-detach` is rejected because the daemon must be running in the background before the TUI can open.

## Manager / Desktop

- `silc manager` opens the manager UI in a browser tab.
- `silc desktop` opens the same UI in a detached native webview window.
- `--share` restarts or starts the daemon in LAN share mode if needed.

## Daemon Control

- `list` prints active sessions from the daemon registry.
- `shutdown` gracefully stops the daemon but preserves records.
- `killall` forcefully terminates sessions and daemon.
- `restart-server` restarts the daemon HTTP server only.
- `resurrect` reloads persisted session records and reconciles them.
- `restart` performs a full daemon restart while preserving share mode.

## Session Commands

- `run` posts JSON `{command, timeout}` to `/run`.
- `out` reads rendered output from `/out`.
- `in` posts raw input bytes to `/in`.
- `status` reads `/status` and prints session metadata.
- `interrupt`, `clear`, `reset`, `resize` map directly to the session API.
- `close`, `kill`, `restart` call daemon lifecycle endpoints.
- `logs` reads the daemon-maintained session log file.
- `web` opens the per-session web UI.
- `start-enter` starts a session and immediately launches the native TUI.
- `tui` launches the native TUI binary.

## Stream Commands

- `stream-file-render` starts overwrite-mode file streaming.
- `stream-file-append` starts append-mode file streaming with deduplication.
- `stream-stop` stops streaming for the named file.
- `stream-status` shows active file streams.

The CLI fetches the session token from `/token` when one is needed for stream calls.

## Native TUI Launch

- `silc tui` resolves a cached or downloaded native binary.
- The binary path is platform-specific and may be installed from GitHub releases.
- Before launch, the CLI checks session `/status` and confirms takeover if another interactive client is already active.
- The launcher passes the session websocket URL directly to the binary.

## Hidden/Internal Commands

- `daemon` is the internal daemon entry point.
- `desktop-window` is an internal helper for the detached native webview.

## Error Handling

- HTTP 410 is treated as a dead session.
- Connection failures print a friendly "session does not exist" message.
- Daemon startup failures print log details before aborting.
- Global/share modes print prominent RCE warnings.
