# Architecture: API Server

This document describes the FastAPI HTTP/WebSocket server. Complete enough to rewrite `silc/api/` from scratch.

---

## Overview

The API server exposes session operations via:

- **REST API** — HTTP endpoints for command execution, output retrieval
- **WebSocket** — Real-time terminal output streaming
- **Static files** — Web UI serving

Each running session gets its own FastAPI app instance bound to its port.

Dormant sessions do not have a per-session FastAPI app until they are materialized.

The daemon may expose session-control HTTP routes on its own public port, but it does not need to proxy WebSocket for non-interactive command execution.

The daemon management API in `silc/daemon/manager.py` is a separate FastAPI app
that owns daemon-wide failure containment for manager operations such as session
creation, restart, resurrection, and shutdown.

---

## Scope Boundary

**This component owns:**
- HTTP endpoint definitions
- Request/response handling
- Authentication (token validation)
- WebSocket connection management
- Static file serving (Web UI)

**This component does NOT own:**
- Session logic (see [arch_core.md](arch_core.md))
- Daemon management (see [arch_daemon.md](arch_daemon.md))
- Streaming service (see [arch_stream.md](arch_stream.md))

**Boundary interfaces:**
- Receives: `SilcSession` instance from daemon
- Exposes: `create_app(session)` factory function

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `fastapi` | HTTP framework | any |
| `uvicorn` | ASGI server | any |
| `pydantic` | Data validation | any |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/core/session.py` | Session operations |
| `silc/core/cleaner.py` | Output cleaning |
| `silc/utils/persistence.py` | Session log reading |
| `silc/stream/api_endpoints.py` | Streaming endpoints |

---

## App Factory

```python
def create_app(session: SilcSession) -> FastAPI:
    app = FastAPI(title=f"SILC Session {session.session_id}")

    # Register endpoints
    # Setup authentication
    # Include streaming router

    return app
```

---

## Authentication

### Token Validation

```python
def _require_token(request: Request) -> None:
    token = session.api_token
    if not token:
        return  # No token required

    client_host = request.client[0] if request.client else None
    if _client_is_local(client_host):
        return  # Localhost bypass

    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing API token")

    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    if parts[1].strip() != token:
        raise HTTPException(status_code=403, detail="Invalid API token")
```

### Localhost Detection

```python
def _client_is_local(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        addr = ip_address(host)
        if addr.is_loopback:
            return True
        if addr.ipv4_mapped and addr.ipv4_mapped.is_loopback:
            return True
    except AddressValueError:
        return False
    return False
```

---

## REST Endpoints

### `GET /status`

Returns session status.

**Response:**
```json
{
  "session_id": "abc12345",
  "port": 20000,
  "title": "my-project",
  "title_updated_at": "2025-01-15T10:30:00Z",
  "alive": true,
  "idle_seconds": 5,
  "waiting_for_input": false,
  "last_line": "user@host:~$",
  "run_locked": false
}
```

**Errors:**
- `410` — Session has ended

### `GET /out`

Returns rendered terminal output.

**Query Parameters:**
- `lines` (int, default: 100) — Number of lines

**Response:**
```json
{
  "output": "terminal output...",
  "lines": 100
}
```

### `GET /raw`

Returns raw terminal output (no rendering).

**Query Parameters:**
- `lines` (int, default: 100) — Number of lines

### `GET /snapshot`

Returns a cached raw PTY byte snapshot for preview rendering.

**Response:** `application/octet-stream`

This endpoint exists only for live sessions because dormant sessions have no session-port server. Any future frozen dormant preview must be served by the daemon, not by a dormant session port.

### `GET /logs`

Returns session log.

**Query Parameters:**
- `tail` (int, default: 100) — Number of lines

### `GET /stream`

Server-sent events stream of terminal output.

**Response:** `text/event-stream`

```
data: terminal output line 1

data: terminal output line 2

```

### `POST /in`

Send raw input to session.

**Request Body:** Plain text

**Query Parameters:**
- `nonewline` (bool, default: false) — Don't append newline

**Response:**
```json
{"status": "sent"}
```

### `POST /run`

Execute a shell command.

**Request Body (plain text):**
```
ls -la
```

**Request Body (JSON):**
```json
{
  "command": "ls -la",
  "timeout": 60
}
```

**Query Parameters:**
- `timeout` (int, default: 60) — Command timeout

**Response:**
```json
{
  "output": "command output...",
  "exit_code": 0,
  "status": "completed"
}
```

### `POST /interrupt`

Send Ctrl+C (SIGINT) to the foreground process in the shell.

**Response:**
```json
{"status": "interrupted"}
```

### `POST /sigterm`

Send SIGTERM to the foreground process group (graceful termination).

This sends a termination signal to the currently running foreground process
in the shell, allowing the session to continue. The session itself is NOT affected.

For session lifecycle operations (close, kill, restart), use the daemon API instead.

**Response:**
```json
{"status": "sigterm_sent"}
```

**Implementation:**
- Unix: Uses `os.killpg()` to signal the process group
- Windows: Uses psutil to gracefully terminate child processes

### `POST /sigkill`

Send SIGKILL to the foreground process group (force termination).

Nuclear option for processes that don't respond to SIGTERM. The session remains
alive and usable.

For session lifecycle operations (close, kill, restart), use the daemon API instead.

**Response:**
```json
{"status": "sigkill_sent"}
```

**Implementation:**
- Unix: Uses `os.killpg()` with `signal.SIGKILL`
- Windows: Uses psutil to forcefully kill child processes

### `POST /clear`

Clear terminal screen.

### `POST /reset`

Reset terminal state.

### `POST /resize`

Resize terminal dimensions.

The session adapter sends permissive CORS headers so the browser manager UI can
call this endpoint directly from `http://127.0.0.1:19999` or other local
origins without CORS failures.

**Query Parameters:**
- `rows` (int, required)
- `cols` (int, required)

### `GET /token`

Return session API token.

### `GET /web`

Serve static Web UI from `static/web/index.html`. Per-port terminal interface.
The page may best-effort read daemon settings for appearance defaults and fall back to built-in defaults if the daemon is unreachable.

---

## WebSocket

### Connection

```
ws://localhost:<port>/ws?token=<token>
```

Token is required for non-localhost connections.

### Binary Envelope

Every application frame is binary:

```text
[4-byte big-endian header length][JSON header UTF-8 bytes][raw payload bytes]
```

The JSON header uses `type`, not `event`.

### Server Messages

- `{"type":"output"}` + raw PTY bytes
- `{"type":"history"}` + `session.buffer.get_bytes()`
- `{"type":"title","title":...,"title_updated_at":...}` + empty payload

### Client Messages

- `{"type":"input","nonewline":true|false}` + UTF-8 input bytes
- `{"type":"load_history"}` + empty payload

### Implementation

- `/ws` accepts only binary application frames.
- PTY bytes are forwarded without UTF-8 decoding on output/history paths.
- Malformed or unsupported frames close the socket with a protocol error.
- The websocket is for interactive sessions; frozen previews use `GET /snapshot`.
- Dormant sessions do not expose websocket or snapshot endpoints because they do not have a live adapter.

---

## Error Handling

### Daemon Request-Failure Boundary

The daemon API installs app-wide exception handlers for both `HTTPException` and
generic `Exception`.

- `HTTPException` is always returned as JSON and must not crash the daemon.
- Unexpected daemon route failures are converted into HTTP 500 JSON responses
  with `error`, `detail`, `operation`, and `traceback` fields.
- Route-local failures in daemon endpoints such as `create_session` and
  `restart_session` must be contained inside the request boundary and must not
  terminate the daemon process.
- Session resurrection failures are quarantined per saved session entry,
  appended to the resurrection result as failures, and logged with full
  traceback detail instead of aborting daemon startup.
- Shutdown and CLI `full-reset` remain the only expected process-exit paths.

### Session Not Alive

```python
def _check_alive():
    if not session.get_status()["alive"]:
        raise HTTPException(status_code=410, detail="Session has ended")
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| `400` | Bad request (invalid parameters) |
| `401` | Unauthorized (missing token) |
| `403` | Forbidden (invalid token) |
| `404` | Not found |
| `410` | Gone (session ended) |
| `500` | Internal server error |

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Localhost bypass | Localhost connections don't require token |
| Token required for remote | Non-localhost connections require valid token |
| Session alive check | All endpoints check session is alive before operating |
| WebSocket cleanup | WebSocket disconnect MUST reset `tui_active`; `/status` exposes the active interactive flag for takeover prompts |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Per-session FastAPI app | Isolation, independent lifecycle | High |
| Bearer token auth | Standard, widely supported | High |
| Localhost bypass | Convenience for local development | High |
| SSE for streaming | Simple, HTTP-compatible | Medium |
| WebSocket for TUI | Bidirectional, low latency | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/api/`
- **Entry points:** `create_app(session)`
- **Key files:**
  - `server.py` — FastAPI app and endpoints
  - `models.py` — Pydantic models
- **Related:** `silc/stream/api_endpoints.py` — Streaming endpoints

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| WebSocket poll interval | event-driven | Output update frequency |
| SSE poll interval | 500ms | Event stream frequency |
| Max request body | None | No explicit limit |
