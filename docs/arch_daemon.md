# Architecture: Daemon

This document describes the daemon architecture. Complete enough to rewrite `silc/daemon/` from scratch.

---

## Overview

The daemon is the root process for SILC. It:

- Exposes a management API on port 19999
- Owns the desired-state record for each session
- Reconciles live runtime to match persisted session records
- Keeps PTY resources alive while a session record exists
- Keeps per-session HTTP servers alive while a session record exists
- Handles graceful shutdown and explicit session destruction

The daemon is both manager and supervisor. There is not a separate supervisor process. The supervisory responsibility is an internal daemon concern.

---

## Scope Boundary

**This component owns:**
- Session desired-state ownership and runtime reconciliation
- PTY supervision and replacement
- Per-session HTTP server orchestration
- PID file management
- Session registry and persistent session records
- Background reconciliation and health recovery
- Signal handling for graceful shutdown

**This component does NOT own:**
- Session internals such as buffer semantics and command execution (see [arch_core.md](arch_core.md))
- Per-session HTTP endpoint logic (see [arch_api.md](arch_api.md))
- CLI parsing (see [arch_cli.md](arch_cli.md))

**Boundary interfaces:**
- Exposes: `SilcDaemon` lifecycle and management API
- Uses: `SilcSession` from core and `create_app(session)` from API

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `uvicorn` | ASGI server | any |
| `fastapi` | HTTP framework | any |
| `psutil` | Process management | any |
| `asyncio` | Async orchestration | stdlib |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/core/session.py` | PTY-backed session runtime |
| `silc/daemon/runtime.py` | Mutable daemon runtime state and generation/backoff helpers |
| `silc/api/server.py` | Per-session FastAPI app factory |
| `silc/utils/persistence.py` | Logging and persistent session records |
| `silc/utils/ports.py` | Port binding and availability |
| `silc/utils/shell_detect.py` | Shell detection and shell metadata |
| `silc/daemon/registry.py` | Desired session registry |

---

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

`SessionEntry` is a desired-state record, not a live runtime object.

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
    last_access: datetime
    title_updated_at: datetime
    is_global: bool
```

### `sessions.json`

Persistent desired-state registry stored at `~/.silc/sessions.json`.

```json
{
  "sessions": [
    {
      "port": 20000,
      "name": "happy-fox-42",
      "title": "happy-fox-42",
      "session_id": "abc12345",
      "shell": "bash",
      "cwd": "/home/user/project",
      "is_global": false,
      "created_at": "2025-01-15T10:30:00Z",
      "title_updated_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Sync behavior:**
- On session create: append entry to `sessions.json`
- On close/kill: remove entry from `sessions.json`
- On shutdown: do nothing; file persists as-is
- This file is the source of truth for desired session existence
- If a record exists, the daemon MUST attempt to realize a matching PTY and per-session server until the record is explicitly removed or marked degraded/broken

### `SessionRuntime`

`SessionRuntime` is derived state. It is disposable and may be recreated repeatedly while the record survives.

```python
@dataclass
class SessionRuntime:
    port: int
    generation: int
    state: str                    # starting, running, degraded, backoff, stopping
    session: SilcSession | None
    server: uvicorn.Server | None
    socket: socket.socket | None
    server_task: asyncio.Task | None
    last_error: str | None
    last_traceback: str | None
    restart_count: int
    next_retry_at: datetime | None
```

### `SilcDaemon`

```python
class SilcDaemon:
    registry: SessionRegistry
    runtime_by_port: Dict[int, SessionRuntime]
    reconciliation_tasks: Dict[int, asyncio.Task]
    _cleanup_tasks: Dict[int, asyncio.Task]
    _daemon_server: uvicorn.Server | None
    _running: bool
    _shutdown_event: asyncio.Event
```

---

## Component Relationships

```text
┌─────────────────────────────────────────────────────────────┐
│                         SilcDaemon                          │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐ │
│  │ Desired       │  │ Runtime Map   │  │ Daemon API      │ │
│  │ Registry      │  │ by Port       │  │ FastAPI         │ │
│  └──────┬────────┘  └──────┬────────┘  └────────┬────────┘ │
│         │                  │                    │          │
│         │        ┌─────────▼─────────┐          │          │
│         │        │ SessionRuntime    │          │          │
│         │        │ generation = N    │          │          │
│         │        └───────┬───────────┘          │          │
│         │                │                      │          │
│         │        ┌───────▼────────┐             │          │
│         │        │ Per-session    │             │          │
│         │        │ server         │             │          │
│         │        │ (messenger)    │             │          │
│         │        └───────┬────────┘             │          │
│         │                │                      │          │
│         │        ┌───────▼────────┐             │          │
│         │        │ PTY-backed     │             │          │
│         │        │ SilcSession    │             │          │
│         │        │ (primary)      │             │          │
│         │        └────────────────┘             │          │
│         │                                       │          │
│  ┌──────▼───────────────────────────────────────▼───────┐  │
│  │ Reconciliation / cleanup / shutdown watchers         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Ownership Model

### Record-as-Truth

The daemon treats session records as desired state:

- If a record exists, the daemon owns recovery of that session.
- If runtime is missing or broken, the daemon attempts to recreate it.
- Removing the record is the real death of the session.

### Resource Priority

Each session has two main runtime resources:

1. **PTY-backed `SilcSession`** — primary resource
2. **Per-session uvicorn server** — messenger resource

The PTY is primary because it owns the shell state. The server is secondary because it only exposes that state over HTTP/WebSocket. Server failure MUST NOT imply session death.

### Replacement Rules

- PTY crash -> replace PTY, preserve record
- Server crash -> replace server, preserve record
- Session restart -> replace PTY, preserve record, reattach messenger
- Session close/kill -> remove record and stop reconciling

### Generation Safety

Every runtime replacement increments a generation number. Cleanup and callbacks from older generations MUST NOT tear down a newer generation.

---

## Daemon API Endpoints

The daemon exposes a management API on port 19999.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve session manager web UI |
| `GET` | `/defaults` | Return UI defaults and installed shell choices |
| `POST` | `/sessions` | Create a new session record and begin realization |
| `GET` | `/sessions` | List desired sessions plus current health/liveness |
| `GET` | `/resolve/{name}` | Resolve session name to session info |
| `POST` | `/sessions/{port}/close` | Gracefully destroy a session |
| `POST` | `/sessions/{port}/kill` | Force kill and destroy a session |
| `POST` | `/sessions/{port}/restart` | Replace PTY, preserve record |
| `POST` | `/restart-server` | Restart daemon HTTP server without killing sessions |
| `POST` | `/resurrect` | Re-read persistent records and reconcile them |
| `POST` | `/shutdown` | Graceful shutdown |
| `POST` | `/killall` | Force kill all |

### `POST /sessions`

**Behavior:**
- Validate requested name, shell, cwd, and port policy
- Persist desired record
- Start or schedule runtime realization
- Return session identity

**Important:** request success means the record now exists. Runtime may still be converging from `starting` to `running`.

### `POST /sessions/{port}/restart`

**Behavior:**
- Preserve: port, name, cwd, shell type, token, and identity record
- Replace the current PTY runtime
- Reattach or recreate the messenger server if needed

### `POST /restart-server`

Restarts the daemon HTTP server layer while keeping session records and PTY runtimes alive.

### `POST /resurrect`

This path is a reconciliation trigger, not a different ownership mode. It causes the daemon to re-read persistent desired records and re-run realization.

---

## Session Lifecycle

### Creation Flow

```text
1. CLI POST /sessions to daemon
   ↓
2. Daemon validates requested identity and launch parameters
   ↓
3. Daemon persists desired session record
   - sessions.json becomes the durable source of truth
   ↓
4. Daemon creates or updates SessionRuntime
   - runtime enters starting state
   ↓
5. Daemon reconciles PTY into existence
   - shell detection / shell selection
   - SilcSession construction
   - session.start()
   ↓
6. Daemon reconciles messenger server into existence
   - reserve socket
   - create_app(session)
   - uvicorn server task
   ↓
7. Runtime transitions to running
   ↓
8. Clients interact with session by port or name
```

### Restart Flow

```text
1. Client POST /sessions/{port}/restart
   ↓
2. Daemon finds desired record
   ↓
3. Daemon stops current PTY runtime for that record
   ↓
4. Daemon increments generation
   ↓
5. Daemon creates fresh PTY runtime
   ↓
6. Daemon reuses or recreates messenger server as needed
   ↓
7. Record survives unchanged
```

### Destruction Flow

```text
1. Trigger: close / kill / shutdown
   ↓
2. Daemon removes desired record
   ↓
3. Daemon stops reconciling runtime for that record
   ↓
4. Daemon stops messenger server
   ↓
5. Daemon closes PTY and kills orphaned processes if needed
   ↓
6. Daemon removes sessions.json entry and logs
```

---

## Reconciliation Model

### Steady-State Reconciliation

The daemon continuously or eventfully reconciles each desired record:

```python
async def reconcile_record(record: SessionEntry) -> None:
    runtime = runtime_by_port[record.port]

    if runtime.state in {"backoff", "degraded"} and retry_not_due(runtime):
        return

    if runtime.session is None or not runtime.session.get_status()["alive"]:
        runtime = await ensure_pty(record, runtime)

    if runtime.server is None or runtime.server_task is None or runtime.server_task.done():
        runtime = await ensure_server(record, runtime)
```

### Startup Reconciliation

On startup, the daemon:

1. reads `sessions.json`
2. recreates desired records
3. creates empty or degraded `SessionRuntime` entries
4. runs the same reconciliation logic used during normal operation

Startup resurrection is therefore ordinary convergence, not a special lifecycle path.

### Backoff and Degraded State

The daemon SHOULD apply bounded backoff for repeated failures such as:

- shell executable missing
- invalid cwd
- repeated PTY launch failure
- repeated socket bind failure

The daemon SHOULD mark records degraded or broken instead of hot-looping forever on unrecoverable configuration errors.

---

## Per-Session Server

Each session gets its own uvicorn server:

```python
def _create_session_server(session: SilcSession, is_global: bool) -> uvicorn.Server:
    app = create_app(session)
    config = uvicorn.Config(
        app,
        host="0.0.0.0" if is_global else "127.0.0.1",
        port=session.port,
        log_level="info",
    )
    return uvicorn.Server(config)
```

The per-session server is a messenger resource:

- replaceable
- restartable independently from the PTY
- not the source of session identity
- not allowed to imply session death by crashing

### Socket Pre-binding

Sockets are reserved before the server starts to prevent port races:

```python
def _reserve_session_socket(port: int, is_global: bool) -> socket.socket:
    return bind_port("0.0.0.0" if is_global else "127.0.0.1", port)
```

The socket belongs to the current runtime generation, not to the durable record itself.

---

## Session Registry

### `SessionRegistry`

The registry is the desired-state index for known sessions.

```python
class SessionRegistry:
    _sessions: Dict[int, SessionEntry]
    _name_index: Dict[str, int]
```

**Operations:**

| Method | Description |
|--------|-------------|
| `add(port, name, session_id, shell_type, cwd, is_global)` | Add desired session record |
| `remove(port)` | Remove desired session record |
| `get(port)` | Get record by port |
| `get_by_name(name)` | Get record by name |
| `name_exists(name)` | Check name collision |
| `list_all()` | List desired records |

The registry answers “what should exist,” not “what is currently healthy.”

---

## Background Tasks

### Reconciliation Loop

```python
async def _reconcile_sessions() -> None:
    while self._running and not self._shutdown_event.is_set():
        for record in self.registry.list_all():
            await reconcile_record(record)
        rotate_daemon_log(max_lines=1000)
        await asyncio.sleep(<reconcile-interval>)
```

### Shutdown Watcher

```python
async def _watch_shutdown() -> None:
    await self._shutdown_event.wait()
    for port in list_all_record_ports():
        await destroy_record_and_runtime(port)
    self._daemon_server.should_exit = True
```

### Hard Exit Watchdog

```python
async def _hard_exit_after(delay: float, exit_code: int) -> None:
    await asyncio.sleep(delay)
    remove_pidfile()
    os._exit(exit_code)
```

---

## Startup Sequence

```text
1. Check for existing daemon process
2. Write PID file
3. Setup signal handlers
4. Create daemon API server
5. Read sessions.json
6. Recreate desired records
7. Start reconciliation and shutdown watchers
8. Serve daemon API
9. On exit, cancel background tasks and remove PID file
```

If some records are invalid or cannot currently be realized, daemon startup still succeeds. Those records remain in degraded or backoff state until fixed or removed.

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Single daemon | Only one daemon process can run at a time |
| PID file exists | PID file MUST exist while daemon is running |
| Record is truth | If a desired record exists, the daemon owns recovery of that session |
| PTY is primary | PTY failure MUST NOT delete the session record |
| Server is messenger | Per-session server failure MUST NOT kill the PTY or remove the record |
| Explicit death only | Only close, kill, or shutdown ends desired session existence |
| Generation safety | Old runtime callbacks MUST NOT tear down newer runtime generations |
| Structured degradation | Unrecoverable configuration SHOULD move a record into degraded/backoff state instead of hot-looping |
| Graceful shutdown | SIGTERM/SIGINT MUST trigger bounded cleanup |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Daemon as root supervisor | Single ownership domain, simpler recovery model | High |
| Record-as-truth | Lets session identity survive runtime replacement | High |
| PTY as primary resource | Shell state matters more than transport layer | High |
| Per-session messenger servers | Isolation and replaceable transport boundary | High |
| Generation-based runtime replacement | Prevents stale cleanup from killing fresh runtime | Medium |
| Backoff/degraded state | Avoids crash loops on bad configuration | Medium |

---

## Implementation Pointers

- **Repos/paths:** `silc/daemon/`
- **Entry points:** `SilcDaemon.start()`
- **Key files:**
  - `manager.py` — daemon orchestration and reconciliation
  - `runtime.py` — per-record runtime state and generation helpers
  - `registry.py` — desired session registry
  - `pidfile.py` — pidfile and daemon process control
- **Related:** `silc/api/server.py` — per-session FastAPI app factory

---

## Error Handling

| Error | Behavior |
|-------|----------|
| Port in use | Return structured client error or relocate according to policy |
| Name already in use | Return 400 error |
| Invalid name format | Return 400 error |
| Invalid shell/cwd | Return structured error and keep daemon alive |
| PTY startup failure | Mark runtime degraded/backoff, preserve record |
| Server task failure | Restart messenger or mark degraded, preserve record |
| Cleanup timeout | Log warning, continue bounded shutdown |
| PID file stale | Clean up and continue startup |
| Name not found | Return 404 error |

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| Reconcile interval | implementation-defined | Must balance responsiveness vs churn |
| Shutdown budget | 30s | Max time for graceful shutdown |
| Cleanup timeout | bounded | Per-resource cleanup must not hang forever |
| Log rotation | 1000 lines | Max lines in daemon log |
| Backoff ceiling | implementation-defined | Prevent hot restart loops |
