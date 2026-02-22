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
    name: str | None = None      # Session name (optional, auto-generated if null)
    is_global: bool = False      # Bind to 0.0.0.0
    token: str | None = None     # Custom API token
    shell: str | None = None     # Shell type (bash, zsh, pwsh, cmd, sh)
    cwd: str | None = None       # Working directory for session
```

### `SessionEntry`

```python
@dataclass
class SessionEntry:
    port: int
    name: str                    # Unique session name (e.g., "happy-fox-42")
    session_id: str
    shell_type: str
    created_at: datetime
    last_access: datetime
```

### `sessions.json`

Persistent session registry stored at `~/.silc/sessions.json`.

```json
{
  "sessions": [
    {
      "port": 20000,
      "name": "happy-fox-42",
      "session_id": "abc12345",
      "shell": "bash",
      "cwd": "/home/user/project",
      "is_global": false,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Sync behavior:**
- On session create: append entry to `sessions.json`
- On session close: remove entry from `sessions.json`
- On shutdown: do nothing (file persists as-is)
- This file is the source of truth for resurrection

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
| `GET` | `/` | Serve session manager web UI |
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions` | List all active sessions |
| `GET` | `/resolve/{name}` | Resolve session name to session info |
| `POST` | `/sessions/{port}/close` | Gracefully close a session |
| `POST` | `/sessions/{port}/kill` | Force kill a session |
| `POST` | `/sessions/{port}/restart` | Restart session (same port/name/cwd/shell) |
| `POST` | `/restart-server` | Restart HTTP server without killing sessions |
| `POST` | `/resurrect` | Restore sessions from sessions.json |
| `POST` | `/shutdown` | Graceful shutdown |
| `POST` | `/killall` | Force kill all |

### `GET /`

**Response:** HTML content from `static/manager/index.html`.

Serves the session manager SPA that allows users to view, create, and manage sessions from a browser.

### `POST /sessions`

**Request Body:**
```json
{
  "port": 20000,        // optional
  "name": "my-project", // optional (auto-generated if null)
  "is_global": false,   // optional
  "token": "abc123",    // optional
  "shell": "bash",      // optional (auto-detect if null)
  "cwd": "/home/user/project"  // optional (daemon cwd if null)
}
```

**Response:**
```json
{
  "port": 20000,
  "name": "my-project",
  "session_id": "abc12345",
  "shell": "bash"
}
```

**Errors:**
- `400` — Name already in use
- `400` — Invalid name format
- `400` — Port in use

### `GET /sessions`

**Response:**
```json
[
  {
    "port": 20000,
    "name": "happy-fox-42",
    "session_id": "abc12345",
    "shell": "bash",
    "idle_seconds": 5,
    "alive": true
  }
]
```

### `GET /resolve/{name}`

Resolve a session name to full session info.

**Response:**
```json
{
  "port": 20000,
  "name": "happy-fox-42",
  "session_id": "abc12345",
  "shell": "bash",
  "idle_seconds": 5,
  "alive": true
}
```

**Errors:**
- `404` — Session name not found

### `POST /sessions/{port}/close`

Gracefully close a session. Works even if the session's HTTP server is unresponsive.

**Response:**
```json
{
  "status": "closed"
}
```

**Errors:**
- `404` — Session not found

**Use case:** Normal session termination. Releases port, cleans up PTY, removes from registry.

### `POST /sessions/{port}/kill`

Force kill a session. Works even if the session's HTTP server is unresponsive.

**Response:**
```json
{
  "status": "killed"
}
```

**Errors:**
- `404` — Session not found

**Use case:** Terminating stuck or dead sessions. Forces PTY termination, kills orphaned processes on port.

### `POST /sessions/{port}/restart`

Restart a session with the same port, name, cwd, and shell type.

**Response:**
```json
{
  "status": "restarted",
  "port": 20000,
  "name": "happy-fox-42",
  "shell": "bash"
}
```

**Errors:**
- `404` — Session not found

**Behavior:**
- Preserves: port, name, cwd, shell type, is_global flag
- Kills old PTY cleanly
- Creates new PTY with same configuration
- Restarts session's HTTP server on same socket

**Use case:** Getting a fresh shell without losing port assignment or session identity.

### `POST /restart-server`

**Response:**
```json
{
  "status": "restarting"
}
```

Restarts the HTTP server layer while keeping all PTY sessions alive. The daemon process continues running; only the uvicorn server is stopped and restarted.

**Use case:** Recovering from HTTP issues without losing shell sessions.

### `POST /resurrect`

Explicitly trigger resurrection from `sessions.json`.

**Response:**
```json
{
  "restored": [
    {"port": 20000, "name": "happy-fox-42", "status": "restored"},
    {"port": 20001, "name": "clever-otter-7", "status": "relocated", "original_port": 20002}
  ],
  "failed": [
    {"name": "stale-session", "reason": "name_collision"}
  ]
}
```

**Use case:** Manual restoration without restarting the daemon.

---

## Session Lifecycle

### Creation Flow

```
1. CLI: silc start my-project --port 20000
   ↓
2. CLI POST /sessions to daemon (port 19999)
   ↓
3. Daemon validates/assigns name
   - If name provided: validate format [a-z][a-z0-9-]*[a-z0-9]
   - Check for name collision → 400 error if exists
   - If no name: generate auto-name (adjective-noun-number)
   ↓
4. Daemon._reserve_session_socket(20000)
   - Bind socket to 127.0.0.1:20000 (or 0.0.0.0 if --global)
   ↓
5. Daemon creates SilcSession
   - detect_shell() → ShellInfo
   - SilcSession(port, name, shell_info, token)
   - await session.start()
   ↓
6. Daemon creates per-session server
   - create_app(session) → FastAPI app
   - uvicorn.Server(app, port=20000)
   ↓
7. Daemon starts server in background
   - asyncio.create_task(server.serve(sockets=[socket]))
   ↓
8. Daemon adds to registry
   - registry.add(port, name, session_id, shell_type)
   ↓
9. Return session info to CLI
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
   g. Remove entry from sessions.json
   h. cleanup_session_log(port)
   ↓
4. Session removed from memory and persistent registry
```

---

## Session Persistence

### File Location

```
~/.silc/sessions.json        # Linux/macOS
%APPDATA%\silc\sessions.json # Windows
```

### Sync Strategy

The daemon maintains a persistent `sessions.json` file that mirrors the in-memory registry:

| Event | Action |
|-------|--------|
| Session created | Append entry to `sessions.json` |
| Session closed | Remove entry from `sessions.json` |
| Daemon shutdown | No action (file persists) |

This ensures the session list survives:
- Graceful shutdown
- Crash / force kill
- PC power loss

### Resurrection

On daemon start, the daemon reads `sessions.json` and attempts to restore each session:

```
1. Read sessions.json
2. For each entry:
   a. Try to bind to original port
   b. If port taken → auto-relocate to next available
   c. If name collision → silent fail, skip entry
   d. Create session with preserved name, shell, cwd
3. Write updated sessions.json with actual ports assigned
```

**Best-effort guarantees:**
- Name is always preserved (unless collision with existing live session)
- Port is attempted, relocated if unavailable
- Shell and cwd are restored exactly

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

In-memory registry tracking active sessions with dual indexing by port and name.

```python
class SessionRegistry:
    _sessions: Dict[int, SessionEntry]   # port → entry
    _name_index: Dict[str, int]           # name → port
```

**Operations:**

| Method | Description |
|--------|-------------|
| `add(port, name, session_id, shell_type)` | Add new session (both indexes) |
| `remove(port)` | Remove session (both indexes) |
| `get(port)` | Get session by port |
| `get_by_name(name)` | Get session by name |
| `name_exists(name)` | Check if name is in use |
| `list_all()` | List all sessions (sorted by port) |
| `cleanup_timeout(timeout_seconds)` | Remove idle sessions |

### Name Generation

Auto-generated names follow the pattern: `adjective-noun-number`

```python
ADJECTIVES = ["happy", "sleepy", "clever", "brave", "calm", "eager", ...]  # ~100 words
NOUNS = ["fox", "bear", "otter", "panda", "tiger", "eagle", ...]  # ~100 words

def generate_name() -> str:
    return f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}-{random.randint(0, 99)}"
```

**Name format validation:** `[a-z][a-z0-9-]*[a-z0-9]`
- Must start with a letter
- Can contain lowercase letters, numbers, and hyphens
- Cannot end with a hyphen
- Case-insensitive (stored as lowercase)

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

    # 4. Load persisted sessions and resurrect
    await _resurrect_sessions()

    # 5. Create daemon API server
    config = uvicorn.Config(daemon_api_app, host="127.0.0.1", port=19999)
    self._daemon_server = uvicorn.Server(config)

    # 6. Start background tasks
    gc_task = asyncio.create_task(self._garbage_collect())
    shutdown_watcher = asyncio.create_task(self._watch_shutdown())

    # 7. Run daemon server
    await self._daemon_server.serve()

    # 8. Cleanup on exit
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
| Unique names | Session names MUST be unique within a daemon instance |
| Name format | Names MUST match `[a-z][a-z0-9-]*[a-z0-9]` pattern |
| Persistent registry | sessions.json MUST always reflect current session state |
| Resurrect best-effort | Resurrection MUST succeed if port available, relocate if not |
| Name preservation | Session names MUST be preserved across resurrect (skip on collision) |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Per-session servers | Isolation, independent lifecycle | High |
| Socket pre-binding | Prevent port race conditions | High |
| PID file | Detect existing daemon, prevent duplicates | High |
| Hard exit watchdog | Handle stuck uvicorn/asyncio on Windows | High |
| 30s shutdown budget | Balance graceful vs. forced termination | Medium |
| Named sessions | Human-friendly identifiers, Docker-style UX | High |
| Dual index (port + name) | Fast lookup by either identifier | High |
| Auto-generated names | Zero-config experience | High |

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
| Name already in use | Return 400 error to client |
| Invalid name format | Return 400 error to client |
| Session creation failure | Close socket, propagate exception |
| Server task failure | Schedule cleanup task |
| Cleanup timeout | Log warning, continue |
| PID file stale | Clean up, allow new daemon |
| Name not found (resolve) | Return 404 error to client |

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| GC interval | 60s | Idle session check frequency |
| Idle timeout | 30 min | Auto-close idle sessions |
| Shutdown budget | 30s | Max time for graceful shutdown |
| Cleanup timeout | 2s | Max time per session cleanup |
| Log rotation | 1000 lines | Max lines in daemon log |
