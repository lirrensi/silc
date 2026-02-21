# Architecture: MCP Server

This document describes the Model Context Protocol (MCP) server implementation. Complete enough to rewrite `silc/mcp/` from scratch.

---

## Overview

The MCP server exposes SILC sessions to AI agents (Claude Code, Cursor, Windsurf) via the Model Context Protocol. It provides:

- **Universal tools** — Work in any context (native shell, SSH, REPLs, interactive apps)
- **Smart wait** — Configurable timeout with output capture
- **Special key support** — Ctrl+C, Ctrl+D, arrow keys, etc.

---

## Scope Boundary

**This component owns:**
- MCP protocol implementation (stdio JSON-RPC)
- Tool definitions and handlers
- Session reference by port number

**This component does NOT own:**
- Session lifecycle (see [arch_daemon.md](arch_daemon.md))
- PTY management (see [arch_core.md](arch_core.md))
- HTTP API (see [arch_api.md](arch_api.md))

**Boundary interfaces:**
- Communicates with: Daemon API (port 19999), Session API (ports 20000+)
- Exposes: MCP tools via stdio

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `mcp` | MCP Python SDK | >=1.0.0 |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/daemon/__init__.py` | Daemon communication |
| `silc/api/server.py` | Session API client |

---

## MCP Tools

### `send(port, text, timeout_ms=5000)`

Send text to session and wait for output.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |
| `text` | string | Yes | — | Text to send (newline appended automatically) |
| `timeout_ms` | int | No | 5000 | Max wait time in milliseconds |

**Response:**
```json
{
  "output": "command output...",
  "lines": 15,
  "alive": true
}
```

**Behavior:**
1. Sends `text + "\n"` to session via `POST /in`
2. Waits up to `timeout_ms` milliseconds
3. Reads output via `GET /out`
4. Returns captured output

**Special case — `timeout_ms=0`:**
- Fire-and-forget mode
- Sends text, returns immediately with empty output
- Use `read()` later to check results

---

### `read(port, lines=100)`

Read current terminal output (read-only).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |
| `lines` | int | No | 100 | Number of lines to return |

**Response:**
```json
{
  "output": "terminal output...",
  "lines": 100
}
```

**MCP Annotation:** `readOnlyHint: true` — safe to auto-approve.

---

### `send_key(port, key)`

Send special key to session.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |
| `key` | string | Yes | — | Key identifier |

**Supported Keys:**
- `ctrl+c`, `ctrl+d`, `ctrl+z`, `ctrl+l`, `ctrl+r`
- `enter`, `escape`, `tab`, `backspace`, `delete`
- `up`, `down`, `left`, `right`
- `home`, `end`

**Response:**
```json
{
  "output": "^C\n>>>",
  "alive": true
}
```

**Implementation:**
- Maps key names to byte sequences
- Sends via `POST /in`
- Reads output after brief delay (100ms)

---

### `list_sessions()`

List all active sessions.

**Response:**
```json
[
  {
    "port": 20000,
    "session_id": "abc12345",
    "alive": true,
    "idle_seconds": 5,
    "shell": "bash"
  }
]
```

**MCP Annotation:** `readOnlyHint: true` — safe to auto-approve.

---

### `start_session(port=None, shell=None, cwd=None)`

Create a new session.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | No | auto | Desired port |
| `shell` | string | No | auto | Shell type (bash, zsh, pwsh, cmd, sh) |
| `cwd` | string | No | MCP server CWD | Working directory for session |

**Response:**
```json
{
  "port": 20001,
  "session_id": "def67890",
  "shell": "bash"
}
```

**Behavior:**
- `cwd=None`: Uses MCP server's current working directory (`os.getcwd()`)
- `shell=None`: Auto-detects shell based on platform and environment

**Implementation:**
- Calls daemon API: `POST http://127.0.0.1:19999/sessions`
- Passes `shell` and `cwd` in request body
- Returns new session info

---

### `close_session(port)`

Close a session gracefully.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |

**Response:**
```json
{
  "status": "closed"
}
```

---

### `get_status(port)`

Get session status.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |

**Response:**
```json
{
  "session_id": "abc12345",
  "port": 20000,
  "alive": true,
  "idle_seconds": 5,
  "last_line": "user@host:~$",
  "run_locked": false
}
```

**MCP Annotation:** `readOnlyHint: true` — safe to auto-approve.

---

### `run(port, command, timeout_ms=60000)`

Execute command with exit code capture (native shell only).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `port` | int | Yes | — | Session port |
| `command` | string | Yes | — | Command to execute |
| `timeout_ms` | int | No | 60000 | Max wait time in milliseconds |

**Response:**
```json
{
  "output": "command output...",
  "exit_code": 0,
  "status": "completed"
}
```

**Status values:**
- `completed` — Command finished
- `timeout` — Timed out
- `busy` — Another run already executing
- `error` — Error (e.g., not in native shell)

**Limitation:**
Only works in native shell where sentinel function is injected. Does NOT work after SSH, inside REPLs, or interactive apps. Use `send()` + `read()` for universal coverage.

---

## Key Mappings

| Key Name | Byte Sequence |
|----------|---------------|
| `ctrl+c` | `\x03` |
| `ctrl+d` | `\x04` |
| `ctrl+z` | `\x1a` |
| `ctrl+l` | `\x0c` |
| `ctrl+r` | `\x12` |
| `enter` | `\r` or `\n` |
| `escape` | `\x1b` |
| `tab` | `\t` |
| `backspace` | `\x7f` or `\x08` |
| `delete` | `\x1b[3~` |
| `up` | `\x1b[A` |
| `down` | `\x1b[B` |
| `right` | `\x1b[C` |
| `left` | `\x1b[D` |
| `home` | `\x1b[H` or `\x1b[1~` |
| `end` | `\x1b[F` or `\x1b[4~` |

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Port as identifier | All tools use port number to identify sessions |
| Universal tools | `send`, `read`, `send_key` work in any context |
| Run limitation | `run` only works in native shell |
| Timeout default | `send` defaults to 5000ms wait |
| Fire-and-forget | `timeout_ms=0` returns immediately |
| Read-only safety | `read`, `list_sessions`, `get_status` are safe to auto-approve |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Port as session identifier | Simpler than UUID, matches existing CLI/API | High |
| Default 5s wait | Matches mcp-interactive-terminal, sensible for most commands | High |
| `timeout_ms=0` for fire-and-forget | Cleaner than separate `no_wait` flag | High |
| `run` as convenience only | Sentinel wrapper only works in native shell | High |
| Separate `send_key` tool | Cleaner for interactive apps, explicit intent | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/mcp/`
- **Entry points:** `silc/mcp/server.py` — MCP server main
- **Related:**
  - `silc/daemon/__init__.py` — Daemon communication
  - `silc/__main__.py` — CLI entry point (add `mcp` subcommand)

---

## Usage Patterns

### Simple Command

```python
result = send(20000, "ls -la")
print(result["output"])
```

### Long-Running Command

```python
result = send(20000, "npm install", timeout_ms=60000)
```

### Interactive App (htop, vim, etc.)

```python
# Start app
send(20000, "htop", timeout_ms=0)

# Check state later
screen = read(20000, lines=40)

# Quit
send_key(20000, "q")
```

### SSH Flow

```python
# Connect
send(20000, "ssh user@remote", timeout_ms=10000)

# Now in remote shell - send/read still work
send(20000, "df -h", timeout_ms=5000)
output = read(20000)
```

### Python REPL

```python
send(20000, "python3", timeout_ms=2000)
send(20000, "import sys", timeout_ms=1000)
send(20000, "sys.version", timeout_ms=1000)
output = read(20000)

# Exit REPL
send_key(20000, "ctrl+d")
```
