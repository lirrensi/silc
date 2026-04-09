# Architecture: CLI

This document describes `silc/__main__.py`.

## Overview

The CLI is a Click-based front end for:

- starting or managing the daemon
- operating on an existing session by port or name through a daemon-backed adapter or direct daemon route
- launching the manager UI, desktop webview, console picker, TUI, and MCP server
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
├── list
├── manager [--share]
├── desktop [--share]
├── pick
├── sessions
│   ├── list
│   ├── wake <targets...|all>
│   ├── unload <targets...|all>
│   ├── restart <targets...|all>
│   ├── close <targets...|all>
│   ├── kill <targets...|all>
│   ├── clear <targets...|all>
│   ├── sigint <targets...|all>
│   ├── sigterm <targets...|all>
│   ├── sigkill <targets...|all>
│   └── resurrect
├── daemon
│   ├── logs [--tail]
│   ├── shutdown
│   ├── restart
│   ├── restart-server
│   └── full-reset
├── mcp
├── settings get|set
├── os-integration install|uninstall
└── <port|name>
    ├── run <command...> [--timeout]
    ├── out [lines]
    ├── in <text...>
    ├── status
    ├── wake
    ├── unload
    ├── restart
    ├── close
    ├── kill
    ├── clear
    ├── sigint
    ├── sigterm
    ├── sigkill
    ├── resize <rows> <cols>
    ├── logs [--tail]
    ├── tui
    ├── web
    ├── desktop
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
- Bulk session commands accept multiple selectors or the reserved `all` selector.

## `silc start`

Behavior:

1. Validate an explicit name if provided.
2. Generate a token for `--global` if one is not supplied.
3. Warn loudly about network exposure when using `--global` or `--share`.
4. Start or reuse the daemon.
5. If no name is provided, derive one from the current folder name.
6. Create the session through the daemon API, sending the CLI process cwd when `--cwd` is omitted.
7. Print connection hints for TUI, web UI, and API access.

Notes:

- Folder-derived names are sanitized and collision-safe (`name`, `name-2`, ...).
- `--no-detach` starts the daemon in-process instead of detaching.
- Session cwd defaults to the caller's current working directory, not the daemon process cwd.
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
- `silc pick` opens a terminal-based session selector. The last row starts a new session in the current cwd and then opens the native TUI.
- `silc <port|name> web` opens the per-session web UI in a browser tab.
- `silc <port|name> desktop` opens the same per-session UI in a detached native webview window.
- `--share` restarts or starts the daemon in LAN share mode if needed.

## Daemon Control

- `sessions list` prints active sessions from the daemon registry; `list` remains a compatibility alias.
- `daemon logs` tails the daemon log file.
- `daemon shutdown` gracefully stops the daemon but preserves records.
- `daemon restart` performs a full daemon restart while preserving share mode.
- `daemon restart-server` restarts the daemon HTTP server only.
- `daemon full-reset` is a CLI-only factory reset that prompts for typed confirmation, stops the daemon, and deletes SILC data.

Legacy aliases remain available but are omitted from the canonical tree.

## Settings Commands

- `silc settings get` reads the daemon-managed shared settings via `GET /settings`.
- `silc settings set <path> <value>` merges a single nested setting path into the daemon-managed settings via `POST /settings`.
- Settings commands are daemon-scoped, not session-scoped, and do not wake dormant sessions.
- If the daemon is unreachable, `settings get` prints the best-effort fallback or an error; `settings set` fails without mutating local browser state.

## Session Commands

- `sessions <port|name> run` posts JSON `{command, timeout}` to `/run` on the port adapter, which forwards to the daemon.
- `sessions <port|name> out` reads rendered output from `/out`.
- `sessions <port|name> in` posts raw input bytes to `/in`.
- `sessions <port|name> status` reads `/status` and prints session metadata.
- `sessions <port|name> wake` activates a dormant session without changing its record.
- `sessions <port|name> unload` stops the live runtime but keeps the session record dormant.
- `sessions <port|name> restart` replaces the runtime while preserving the record.
- `sessions <port|name> close`, `kill`, `sigint`, `sigterm`, `sigkill`, `clear`, and `resize` map directly to the adapter surface or daemon lifecycle.
- `sessions <port|name> logs` reads the daemon-maintained session log file.
- `sessions <port|name> web` opens the per-port session UI.
- `sessions <port|name> tui` launches the native TUI binary.
- All session-targeted commands wake dormant sessions synchronously before continuing, except `unload`, `close`, and `kill`.

## Stream Commands

- `stream-file-render` starts overwrite-mode file streaming.
- `stream-file-append` starts append-mode file streaming with deduplication.
- `stream-stop` stops streaming for the named file.
- `stream-status` shows active file streams.
- Stream commands also wake dormant sessions before calling the session surface.

The CLI fetches the session token from `/token` when one is needed for stream calls.

## Native TUI Launch

- `silc tui` resolves a cached or downloaded native binary.
- The binary path is platform-specific and may be installed from GitHub releases.
- Before launch, the CLI checks session `/status` and confirms takeover if another interactive client is already active.
- `tui` wakes dormant sessions before checking takeover or launching the binary.
- The launcher passes the session websocket URL directly to the binary.

## Hidden/Internal Commands

- `daemon` is the internal daemon entry point.
- `desktop-window` is an internal helper for the detached native webview.

## Error Handling

- HTTP 410 is treated as a dead session.
- Connection failures print a friendly "session does not exist" message.
- Daemon startup failures print log details before aborting.
- Global/share modes print prominent RCE warnings.
