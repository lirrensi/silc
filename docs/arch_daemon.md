# Architecture: Daemon

This document describes the daemon architecture. Complete enough to rewrite `silc/daemon/` from scratch.

---

## Overview

The daemon is the central process that manages multiple shell sessions. It:

- Exposes a management API on port 19999
- Creates and destroys sessions on demand
- Launches per-session HTTP servers
- Performs garbage collection of idle sessions
- Handles graceful shutdown

---

## Scope Boundary

**This component owns:**
- Session lifecycle management (create, destroy, list)
- Per-session HTTP server orchestration
- PID file management
- Session registry
- Garbage collection of idle sessions
- Signal handling for graceful shutdown

**This component does NOT own:**
- Session internals (see [arch_core.md](arch_core.md))
- HTTP endpoint logic (see [arch_api.md](arch_api.md))
- CLI parsing (see [arch_cli.md](arch_cli.md))

**Boundary interfaces:**
- Exposes: `SilcDaemon` class with `start()`, `is_running()`
- Uses: `SilcSession` from arch_core, `create_app()` from arch_api

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `uvicorn` | ASGI server | any |
| `fastapi` | HTTP framework | any |
| `psutil` | Process management | any |
| `asyncio` | Async I/O | stdlib |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/core/session.py` | Session implementation |
| `silc/api/server.py` | FastAPI app factory |
| `silc/utils/persistence.py` | Logging, data directories |
| `silc/utils/ports.py` | Port management |
| `silc/utils/shell_detect.py` | Shell detection |

---

## Data Models

### `SessionCreateRequest`

```python
class SessionCreateRequest(BaseModel):
    port: int | None = None      # Requested port (optional)
    is_global: bool = False      # Bind to 0.0.0.0
    token: str | None = None     # Custom API token
```

### `SessionEntry`

```python
@dataclass
class SessionEntry:
    port: int
    session_id: str
    shell_type: str
    created_at: datetime
    last_access: datetime
```

### `SilcDaemon`

```python
class SilcDaemon:
    registry: SessionRegistry
    sessions: Dict[int, SilcSession]
    servers: Dict[int, uvicorn.Server]
    _session_sockets: Dict[int, socket.socket]
    _session_tasks: Dict[int, asyncio.Task]
    _cleanup_tasks: Dict[int, asyncio.Task]
    _daemon_server: uvicorn.Server | None
    _running: bool
    _shutdown_event: asyncio.Event
```

---

## Component Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                        SilcDaemon                            │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Registry   │  │   PIDFile   │  │   Daemon API        │  │
│  │(SessionReg) │  │(pidfile.py) │  │   (FastAPI)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                              │               │
│                    ┌─────────────────────────┼───────────┐   │
│                    │                         │           │   │
│               ┌────▼────┐              ┌─────▼─────┐     │   │
│               │ Session │              │  Session  │     │   │
│               │ Server  │              │  Server   │     │   │
│               │(uvicorn)│              │ (uvicorn) │     │   │
│               └────┬────┘              └─────┬─────┘     │   │
│                    │                         │           │   │
│               ┌────▼────┐              ┌─────▼─────┐     │   │
│               │ Session │              │  Session  │     │   │
│               │  (PTY)  │              │   (PTY)   │     │   │
│               └─────────┘              └───────────┘     │   │
│                                                          │   │
│  ┌─────────────────────────────────────────────────────┐ │   │
│  │              Background Tasks                        │ │   │
│  │  • _garbage_collect() — idle session cleanup         │ │   │
│  │  • _watch_shutdown() — signal handling               │ │   │
│  └─────────────────────────────────────────────────────┘ │   │
└─────────────────────────────────────────────────────────────┘
```

---

## Daemon API Endpoints

The daemon exposes a management API on port 19999.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions` | List all active sessions |
| `DELETE` | `/sessions/{port}` | Close a specific session |
| `POST` | `/shutdown` | Graceful shutdown |
| `POST` | `/killall` | Force kill all |

### `POST /sessions`

**Request Body:**
```json
{
  "port": 20000,        // optional
  "is_global": false,   // optional
  "token": "abc123"     // optional
}
```

**Response:**
```json
{
  "port": 20000,
  "session_id": "abc12345",
  "shell": "bash"
}
```

### `GET /sessions`

**Response:**
```json
[
  {
    "port": 20000,
    "session_id": "abc12345",
    "shell": "bash",
    "idle_seconds": 5,
    "alive": true
  }
]
```

---

## Session Lifecycle

### Creation Flow

```
1. CLI: silc start --port 20000
   ↓
2. CLI POST /sessions to daemon (port 19999)
   ↓
3. Daemon._reserve_session_socket(20000)
   - Bind socket to 127.0.0.1:20000 (or 0.0.0.0 if --global)
   ↓
4. Daemon creates SilcSession
   - detect_shell() → ShellInfo
   - SilcSession(port, shell_info, token)
   - await session.start()
   ↓
5. Daemon creates per-session server
   - create_app(session) → FastAPI app
   - uvicorn.Server(app, port=20000)
   ↓
6. Daemon starts server in background
   - asyncio.create_task(server.serve(sockets=[socket]))
   ↓
7. Daemon adds to registry
   - registry.add(port, session_id, shell_type)
   ↓
8. Return session info to CLI
```

### Cleanup Flow

```
1. Trigger: close/kill/shutdown request OR idle timeout
   ↓
2. Daemon._ensure_cleanup_task(port)
   - Creates cleanup task if not exists
   ↓
3. Daemon._cleanup_session(port)
   a. server.should_exit = True
   b. Close listening socket
   c. Cancel server task
   d. await session.close()
   e. Kill orphaned processes on port
   f. registry.remove(port)
   g. cleanup_session_log(port)
   ↓
4. Session removed from memory
```

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

**Socket Pre-binding:**

Sockets are pre-bound before server start to prevent race conditions:

```python
def _reserve_session_socket(port: int, is_global: bool) -> socket.socket:
    sock = bind_port("0.0.0.0" if is_global else "127.0.0.1", port)
    self._session_sockets[port] = sock
    return sock
```

---

## PID File Management

### Location

```
~/.silc/daemon.pid        # Linux/macOS
%APPDATA%\silc\daemon.pid # Windows
```

### Operations

| Function | Description |
|----------|-------------|
| `write_pidfile(pid)` | Write daemon PID to file |
| `read_pidfile()` | Read PID from file, return None if not found |
| `remove_pidfile()` | Remove PID file |
| `is_daemon_running()` | Check if daemon process is running |
| `kill_daemon()` | Kill daemon process tree |

### Process Killing

```python
def kill_daemon(*, timeout: float = 2.0, force: bool = True, port: int | None) -> bool:
    # 1. Read PID from file
    # 2. Find PIDs listening on daemon port (fallback)
    # 3. Terminate process tree (children first)
    # 4. Wait for processes to exit
    # 5. Force kill if still alive
    # 6. Remove PID file
```

---

## Session Registry

### `SessionRegistry`

In-memory registry tracking active sessions.

**Operations:**

| Method | Description |
|--------|-------------|
| `add(port, session_id, shell_type)` | Add new session |
| `remove(port)` | Remove session |
| `get(port)` | Get session by port |
| `list_all()` | List all sessions (sorted by port) |
| `cleanup_timeout(timeout_seconds)` | Remove idle sessions |

---

## Background Tasks

### Garbage Collection

```python
async def _garbage_collect():
    while self._running and not self._shutdown_event.is_set():
        await asyncio.sleep(60)

        # Cleanup timed out sessions
        cleaned_ports = self.registry.cleanup_timeout(timeout_seconds=1800)
        for port in cleaned_ports:
            await self._ensure_cleanup_task(port)

        # Rotate daemon log
        rotate_daemon_log(max_lines=1000)
```

### Shutdown Watcher

```python
async def _watch_shutdown():
    await self._shutdown_event.wait()

    # Cleanup all sessions with 30s budget
    for port in list(self.sessions.keys()):
        await self._ensure_cleanup_task(port)

    self._daemon_server.should_exit = True
```

### Hard Exit Watchdog

```python
async def _hard_exit_after(delay: float, exit_code: int):
    await asyncio.sleep(delay)
    remove_pidfile()
    os._exit(exit_code)
```

---

## Signal Handling

```python
def _setup_signals():
    def handle_signal(signum, frame):
        self._shutdown_event.set()
        self._daemon_server.should_exit = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
```

---

## Startup Sequence

```python
async def start():
    # 1. Check for existing daemon
    if read_pidfile():
        raise RuntimeError("Daemon already running")

    # 2. Write PID file
    write_pidfile(os.getpid())

    # 3. Setup signal handlers
    _setup_signals()

    # 4. Create daemon API server
    config = uvicorn.Config(daemon_api_app, host="127.0.0.1", port=19999)
    self._daemon_server = uvicorn.Server(config)

    # 5. Start background tasks
    gc_task = asyncio.create_task(self._garbage_collect())
    shutdown_watcher = asyncio.create_task(self._watch_shutdown())

    # 6. Run daemon server
    await self._daemon_server.serve()

    # 7. Cleanup on exit
    gc_task.cancel()
    shutdown_watcher.cancel()
    remove_pidfile()
```

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Single daemon | Only one daemon process can run at a time |
| PID file exists | PID file MUST exist while daemon is running |
| Bounded cleanup | Session cleanup MUST complete within timeout |
| Socket pre-binding | Session sockets MUST be bound before server start |
| Graceful shutdown | SIGTERM/SIGINT MUST trigger graceful cleanup |
| Hard exit fallback | Hard exit watchdog MUST ensure process termination |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Per-session servers | Isolation, independent lifecycle | High |
| Socket pre-binding | Prevent port race conditions | High |
| PID file | Detect existing daemon, prevent duplicates | High |
| Hard exit watchdog | Handle stuck uvicorn/asyncio on Windows | High |
| 30s shutdown budget | Balance graceful vs. forced termination | Medium |

---

## Implementation Pointers

- **Repos/paths:** `silc/daemon/`
- **Entry points:** `SilcDaemon.start()`
- **Key files:**
  - `manager.py` — Daemon orchestration
  - `registry.py` — Session registry
  - `pidfile.py` — PID file management
- **Related:** `silc/api/server.py` — FastAPI app factory

---

## Error Handling

| Error | Behavior |
|-------|----------|
| Port in use | Return 400 error to client |
| Session creation failure | Close socket, propagate exception |
| Server task failure | Schedule cleanup task |
| Cleanup timeout | Log warning, continue |
| PID file stale | Clean up, allow new daemon |

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| GC interval | 60s | Idle session check frequency |
| Idle timeout | 30 min | Auto-close idle sessions |
| Shutdown budget | 30s | Max time for graceful shutdown |
| Cleanup timeout | 2s | Max time per session cleanup |
| Log rotation | 1000 lines | Max lines in daemon log |
