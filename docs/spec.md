# SILC Behavior Specification

SILC manages shell sessions through a daemon, per-session HTTP APIs, and multiple client surfaces.

## Core Concepts

- **Daemon**: owns the desired session registry, manages lifecycle, and serves the manager UI.
- **Session**: a named shell bound to a port with a live PTY and persisted record.
- **Runtime**: the live, replaceable process/server pair for a session.
- **Manager UI**: the browser/native desktop session manager.

## Session Identity

- Sessions are identified by **port** and **name**.
- Ports are auto-selected from `20000..21000` unless explicitly requested.
- Explicit names must match `[a-z][a-z0-9-]*[a-z0-9]`.
- If the CLI creates a session without a name, it derives one from the current folder.
- If the daemon API creates a session without a name, it generates a unique Docker-style name like `happy-fox-42`.

## Session Lifecycle

- Creating a session writes a desired-state record and realizes a live PTY plus per-session HTTP server.
- If the PTY dies, the daemon recreates it while preserving the record.
- If the per-session HTTP server dies, the daemon recreates it while preserving the record.
- `close` removes the desired record and stops reconciling the session.
- `kill` forcefully destroys the session and removes the record.
- `restart` replaces the PTY/server but preserves the record, port, name, cwd, and shell.
- `shutdown` stops live runtime but preserves records.
- `killall` destroys live sessions and exits the daemon.
- `resurrect` reloads persisted records and reconciles them.
- Sessions do not auto-expire; idle tracking is informational only.

## Daemon API

The daemon listens on `19999` and exposes:

- `POST /sessions` — create session
- `GET /sessions` — list desired sessions plus live health
- `GET /defaults` — manager defaults and shell choices
- `GET /resolve/{name}` — resolve a name to a session record
- `POST /sessions/{port}/rename` — rename a session
- `POST /sessions/reorder` — reorder sessions
- `POST /sessions/{port}/close` — close session
- `POST /sessions/{port}/kill` — kill session
- `POST /sessions/{port}/restart` — restart session
- `POST /restart-server` — restart daemon HTTP server only
- `POST /resurrect` — reload persisted records and reconcile
- `POST /shutdown` — graceful daemon shutdown
- `POST /killall` — force kill daemon and sessions
- `GET /events` — binary websocket stream of manager events

## Session API

Each session has its own HTTP server on the session port.

### Auth

- Requests from localhost do not need a token.
- Remote requests require `Authorization: Bearer <token>`.
- The websocket also accepts `?token=...`.

### Endpoints

- `GET /status` — session metadata and liveness
- `GET /out?lines=N` — rendered output
- `GET /raw?lines=N` — raw output
- `GET /snapshot` — raw PTY bytes for previews
- `GET /logs?tail=N` — session log tail
- `GET /stream` — SSE stream of cleaned output
- `POST /in` — send input
- `POST /run` — run a command
- `POST /interrupt` — send Ctrl+C
- `POST /sigterm` — terminate foreground process tree gently
- `POST /sigkill` — kill foreground process tree forcefully
- `POST /clear` — clear screen
- `POST /reset` — reset terminal state
- `POST /resize?rows=&cols=` — resize terminal
- `GET /token` — expose current token to local helpers
- `GET /web` — static per-session web UI

### `/run`

- Accepts plain text or JSON `{command, timeout}`.
- Uses sentinel markers to capture exit code and output.
- Returns `completed`, `timeout`, `busy`, or `error`.
- Output is capped at 5 MB; overflow interrupts the shell and returns an error.

### `/status`

Includes: `session_id`, `port`, `name`, `title`, `cwd`, `title_updated_at`, `alive`, `idle_seconds`, `waiting_for_input`, `last_line`, `run_locked`.

## WebSocket Protocol

- URL: `ws://127.0.0.1:<port>/ws`
- Session token is provided via query string when needed.
- Frames are binary:

```text
[4-byte big-endian header length][JSON header UTF-8 bytes][raw payload bytes]
```

### Client → Server

- `input` with optional `nonewline`
- `load_history`

### Server → Client

- `output`
- `history`
- `title`
- `cwd`

`mode=interactive` claims the live terminal; `mode=preview` is read-only.

## CLI Behavior

- `silc start` starts the daemon if needed and creates a session.
- `silc manager` opens the manager UI in a browser.
- `silc desktop` opens the manager UI in a native webview.
- `silc list`, `shutdown`, `killall`, `restart-server`, `resurrect`, and `restart` operate on the daemon.
- Session-targeted commands accept either a port or a resolved name.
- `silc tui` launches the native TUI binary.
- `silc open` is deprecated and launches the legacy Textual TUI.

## Stream-to-File

- Render mode overwrites a file with the current terminal snapshot.
- Append mode appends novel lines using exact + fuzzy deduplication.
- CLI commands are `stream-file-render`, `stream-file-append`, `stream-stop`, and `stream-status`.
- The CLI fetches the session token from `/token` when needed.
- Current implementation accepts rotation-related config fields but does not enforce rotation.

## MCP Server

The MCP server exposes:

- `send`
- `read`
- `send_key`
- `list_sessions`
- `start_session`
- `close_session`
- `get_status`
- `resize`
- `run`

`send` is universal and waits for output; `run` is convenience only and works best in native shells.

## Invariants

- One live `run` at a time per session.
- Session records outlive runtime failures.
- Daemon route failures are contained as JSON errors.
- WebSocket disconnects clear interactive ownership.
- Idle sessions are never auto-closed.
