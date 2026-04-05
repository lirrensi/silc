# Architecture: Daemon

This document describes `silc/daemon/`.

## Overview

The daemon is the root process for SILC. It:

- serves the manager UI and daemon API on port `19999`
- owns the desired-state registry for sessions
- reconciles live runtime against persisted records
- recreates PTYs and per-session servers when they fail
- performs bounded cleanup, shutdown, and resurrection

There is no separate supervisor process; supervision is an internal daemon concern.

## Scope Boundary

Owns:

- desired session records and persistence
- runtime generation/backoff state
- PTY + session server realization
- manager UI serving and daemon API routes
- daemon event broadcasting
- pidfile management and signal handling

Does not own:

- per-session shell semantics (`silc/core/`)
- per-session HTTP/WebSocket endpoint behavior (`silc/api/server.py`)
- CLI parsing (`silc/__main__.py`)

## Key Modules

| Module | Role |
|---|---|
| `silc/daemon/manager.py` | `SilcDaemon` and daemon API |
| `silc/daemon/registry.py` | Desired session registry |
| `silc/daemon/runtime.py` | Mutable runtime state and backoff helpers |
| `silc/daemon/events.py` | Manager websocket events and binary frame encoding |
| `silc/daemon/pidfile.py` | pidfile helpers |

## Data Models

### `SessionCreateRequest`

```python
class SessionCreateRequest(BaseModel):
    port: int | None = None
    name: str | None = None
    is_global: bool = False
    token: str | None = None
    shell: str | None = None
    cwd: str | None = None
```

### `SessionEntry`

Desired-state record stored by `SessionRegistry`.

```python
@dataclass
class SessionEntry:
    port: int
    name: str
    session_id: str
    shell_type: str
    cwd: str | None
    title: str
    created_at: datetime
    is_global: bool = False
    last_access: datetime
    title_updated_at: datetime
```

### `SessionRuntime`

Live state that may be recreated repeatedly while the record survives.

```python
@dataclass
class SessionRuntime:
    port: int
    generation: int
    state: SessionState
    session: SilcSession | None
    server: uvicorn.Server | None
    socket: socket.socket | None
    server_task: asyncio.Task | None
    last_error: str
    last_traceback: str
    restart_count: int
    next_retry_at: datetime | None
    name: str
    shell_type: str
    cwd: str | None
    api_token: str | None
    title: str
    is_global: bool
```

### `SilcDaemon`

Important fields:

```python
registry: SessionRegistry
sessions: dict[int, SilcSession]
servers: dict[int, uvicorn.Server]
runtime_by_port: dict[int, SessionRuntime]
events: DaemonEventBroadcaster
_session_sockets: dict[int, socket.socket]
_session_tasks: dict[int, asyncio.Task]
_cleanup_tasks: dict[int, asyncio.Task]
_daemon_api_app: FastAPI
```

## Persistence

- Desired records are persisted to `sessions.json` in the SILC data dir.
- Writes are atomic when possible.
- Removing a record is what actually ends a session.
- Shutdown does **not** delete records.

## Runtime Model

- A record is truth; runtime is disposable.
- PTY failure triggers PTY recreation.
- Server failure triggers server recreation.
- Generation counters prevent stale cleanup from killing newer runtime.
- Runtime failures enter backoff and are retried later.

## Startup Flow

1. Write/read pidfile and abort if another daemon is alive.
2. Load persisted desired records.
3. Reconcile loaded records into live runtime.
4. Start the daemon API server.
5. Start periodic log rotation, shutdown watcher, restart watcher, and reconcile loop.

If `share_mode` is enabled, the daemon and session servers bind to LAN-reachable addresses and the manager URL reflects the host IP.

## Daemon API

The daemon serves the manager UI under `/ui/`.

- `/` redirects to `/ui/`
- `/ui`, `/ui/`, `/ui/{path:path}` serve the SPA
- `/ui/assets` serves compiled assets

API routes:

- `POST /sessions` — create a session
- `GET /sessions` — list sessions with live health
- `GET /defaults` — defaults for manager UI helpers
- `GET /resolve/{name}` — name lookup
- `POST /sessions/{port}/rename` — rename in place
- `POST /sessions/reorder` — reorder registry order
- `POST /sessions/{port}/close` — remove record and stop reconciling
- `POST /sessions/{port}/kill` — force kill and remove record
- `POST /sessions/{port}/restart` — replace PTY/server, preserve record
- `POST /restart-server` — restart daemon HTTP server only
- `POST /resurrect` — reload `sessions.json` and reconcile
- `POST /shutdown` — graceful shutdown, preserve records
- `POST /killall` — force kill everything
- `GET /events` — manager websocket event stream

## Session Creation Rules

- Explicit names are validated with `is_valid_name()`.
- If no name is provided, the daemon generates a unique Docker-style name.
- If no port is provided, the daemon scans `20000..21000` for a free port.
- `MAX_SESSIONS` caps the total registry size.
- `--global` or daemon share mode causes session servers to bind externally.

## Reconciliation Rules

- Missing PTY -> recreate session.
- Missing server -> recreate server.
- Stopping/stopped runtimes are skipped.
- Backoff prevents hot-loop retries after repeated failure.
- The runtime is updated from live title/cwd callbacks when those values change.

## Events

Manager events are binary framed with the shared SILC envelope.

Important event types:

- `session/snapshot`
- `session/created`
- `session/started`
- `session/updated`
- `session/renamed`
- `session/title_changed`
- `session/cwd_changed`
- `session/reordered`
- `session/restarted`
- `session/removed`

## Shutdown and Hard Exit

- `shutdown` is bounded and preserves records.
- `killall` is bounded and removes live runtime aggressively.
- On some platforms a delayed hard exit is scheduled so a wedged process does not keep the daemon alive.
- Signal handlers set the shutdown event and let the normal shutdown path finish.
