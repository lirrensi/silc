# Architecture: API Server

This document describes the FastAPI HTTP/WebSocket server. Complete enough to rewrite `silc/api/` from scratch.

---

## Overview

The API server exposes session operations via:

- **REST API** — HTTP endpoints for command execution, output retrieval
- **WebSocket** — Real-time terminal output streaming
- **Static files** — Web UI serving

Each session gets its own FastAPI app instance bound to its port.

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

Send Ctrl+C to session.

### `POST /clear`

Clear terminal screen.

### `POST /reset`

Reset terminal state.

### `POST /resize`

Resize terminal dimensions.

**Query Parameters:**
- `rows` (int, required)
- `cols` (int, required)

### `POST /close`

Gracefully close session.

### `POST /kill`

Force kill session.

### `GET /token`

Return session API token.

### `GET /web`

Serve static Web UI.

---

## WebSocket

### Connection

```
ws://localhost:<port>/ws?token=<token>
```

Token is required for non-localhost connections.

### Server Messages

**Output update:**
```json
{
  "event": "update",
  "data": "terminal output..."
}
```

**History (on request):**
```json
{
  "event": "history",
  "data": "full terminal history..."
}
```

### Client Messages

**Send input:**
```json
{
  "event": "type",
  "text": "ls -la",
  "nonewline": false
}
```

**Request history:**
```json
{
  "event": "load_history"
}
```

### Implementation

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not _verify_websocket_token(websocket):
        await websocket.close(code=1008, reason="Invalid API token")
        return

    await websocket.accept()
    session.tui_active = True

    async def send_updates():
        cursor = session.buffer.cursor
        while True:
            new_bytes, cursor = session.buffer.get_since(cursor)
            if new_bytes:
                await websocket.send_json({
                    "event": "update",
                    "data": new_bytes.decode("utf-8", errors="replace")
                })
            await asyncio.sleep(0.1)

    sender_task = asyncio.create_task(send_updates())
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            # Handle message...
    except WebSocketDisconnect:
        pass
    finally:
        session.tui_active = False
        sender_task.cancel()
```

---

## Error Handling

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
| WebSocket cleanup | WebSocket disconnect MUST reset `tui_active` |

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
| WebSocket poll interval | 100ms | Output update frequency |
| SSE poll interval | 500ms | Event stream frequency |
| Max request body | None | No explicit limit |
