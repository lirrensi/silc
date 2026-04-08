# Architecture: Daemon

This document describes `silc/daemon/`.

## Overview

The daemon is the root process for SILC. It:

- serves the manager UI and daemon API on port `19999`
- owns the desired-state registry for sessions
- owns the shared daemon settings store for manager and terminal preferences
- loads persisted records as dormant desired sessions on boot
- materializes live runtime against persisted records on explicit activation
- recreates PTYs and lightweight port adapters when they fail
- performs bounded cleanup, graceful snapshot save, shutdown, and resurrection
- centralizes session-target resolution (port first, then name)

There is no separate supervisor process; supervision is an internal daemon concern.

## Scope Boundary

Owns:

- desired session records and persistence
- frozen snapshot file ownership and lookup
- runtime generation/backoff state
- PTY + session runtime realization
- lightweight per-port adapter lifecycle
- manager UI serving and daemon API routes
- daemon event broadcasting
- pidfile management and signal handling
- shared session-target resolution

Does not own:

- per-session shell semantics (`silc/core/`)
- per-session HTTP/WebSocket endpoint behavior (`silc/api/server.py`)
- CLI parsing (`silc/__main__.py`)

## Key Modules

| Module | Role |
|---|---|
| `silc/daemon/manager.py` | `SilcDaemon` and daemon API |
| `silc/daemon/registry.py` | Desired session registry |
| `silc/daemon/settings.py` | Shared daemon settings model and merge helpers |
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

Persisted snapshot bytes are stored separately from `SessionEntry` metadata and are keyed by `session_id` so dormant sessions can remain disk-backed until requested even if ports change.

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

### `DaemonSettings`

Shared settings persisted to `settings.json` in the SILC data dir.

```python
@dataclass
class DaemonSettings:
    ui: dict[str, Any]
    terminal: dict[str, Any]
```

### `SilcDaemon`

Important fields:

```python
registry: SessionRegistry
settings: DaemonSettings
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
- Shared settings are persisted separately to `settings.json` in the SILC data dir.
- Frozen raw PTY snapshots from graceful shutdown/restart are persisted as separate per-session files keyed by `session_id`.
- Writes are atomic when possible.
- Removing a record is what actually ends a session.
- Shutdown does **not** delete records.
- Shared settings writes use the same daemon metadata lock discipline as registry writes.
- Daemon startup restoration garbage-collects orphaned snapshot files whose `session_id` is not present in the desired registry.

## Runtime Model

- A record is truth; runtime is disposable.
- Dormant records have no live PTY, no live adapter, and no in-memory snapshot payload until explicitly activated.
- PTY failure triggers PTY recreation.
- Adapter failure triggers adapter recreation.
- Generation counters prevent stale cleanup from killing newer runtime.
- Runtime failures enter backoff and are retried later.

## Startup Flow

1. Write/read pidfile and abort if another daemon is alive.
2. Load persisted desired records.
3. Garbage-collect orphaned snapshot files that do not match any restored `session_id`.
4. Load shared settings from `settings.json` and merge them over built-in defaults.
5. Keep loaded records dormant by default.
6. Record whether frozen snapshot files exist, without loading snapshot bytes into memory.
7. Start the daemon API server.
8. Start periodic log rotation, shutdown watcher, restart watcher, and reconcile loop.

If `share_mode` is enabled, the daemon and adapters bind to LAN-reachable addresses and the manager URL reflects the host IP.

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
- `GET /settings` — return shared daemon settings
- `POST /settings` — merge shared daemon settings
- `POST /sessions/{port}/rename` — rename in place
- `POST /sessions/reorder` — reorder registry order
- `POST /sessions/{port}/close` — remove record and stop reconciling
- `POST /sessions/{port}/kill` — force kill and remove record
- `POST /sessions/{port}/restart` — replace PTY/server, preserve record
- `POST /restart-server` — restart daemon HTTP server only
- `POST /resurrect` — reload `sessions.json` and materialize desired sessions
- `POST /shutdown` — graceful shutdown, preserve records
- `POST /killall` — clear all sessions and session artifacts, keep daemon alive
- `GET /events` — manager websocket event stream

Session control routes are also available on the daemon port using a shared `{key}` resolver. Lightweight loopback adapters may forward port-based traffic into these daemon routes so client URLs stay stable.

## Session Creation Rules

- Explicit names are validated with `is_valid_name()`.
- If no name is provided, the daemon generates a unique Docker-style name.
- If no port is provided, the daemon scans `20000..21000` for a free port.
- Numeric-only names are invalid.
- Folder-derived auto-names that sanitize to digits only must be rewritten with a non-numeric marker, e.g. `folder-111`.
- `MAX_SESSIONS` caps the total registry size.
- `--global` or daemon share mode causes adapters to bind externally.

## Session Resolution

- `resolve_session_target(key)` centralizes all daemon session lookup.
- Numeric keys are resolved as ports first.
- Non-numeric keys are resolved by name.
- All daemon session-control routes use the same resolver.

## Reconciliation Rules

- Dormant records stay unloaded until explicit activation or all-session resurrection.
- Missing PTY -> recreate session.
- Missing adapter -> recreate adapter.
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

- `shutdown` is bounded, saves frozen raw snapshots for live sessions during graceful stop, and preserves records as dormant entries.
- `killall` is bounded and aggressively removes live runtime plus session records/artifacts without terminating the daemon.
- On some platforms a delayed hard exit is scheduled so a wedged process does not keep the daemon alive.
- Signal handlers set the shutdown event and let the normal shutdown path finish.
