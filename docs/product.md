# SILC (Shared Interactive Linked CMD) — Product Specification

**Bridge your terminal with the world — let humans and AI agents collaborate in the same shell.**

---

## Overview

SILC transforms a terminal session into an HTTP-accessible interface, enabling:

- **AI agents** to execute commands and read output programmatically
- **Teams** to share shell sessions across machines
- **Automation tools** to interact with shells via REST API
- **Monitoring dashboards** to display terminal output in real-time

Unlike tmux, screen, or SSH, SILC provides:
- **HTTP API** — Programmatic access to any shell command
- **Real-time streaming** — WebSocket support for live output
- **Cross-platform** — Works on Windows, Linux, macOS
- **Agent-friendly** — Designed for AI/LLM integration
- **Simple setup** — One command to start, no complex configuration

---

## Features

### Core Capabilities

- **One-command setup** — Start daemon and create sessions instantly
- **HTTP API** — Full REST API for all shell operations
- **WebSocket Streaming** — Real-time terminal output
- **Native TUI** — Terminal UI for interactive sessions
- **Web UI** — Browser-based terminal interface
- **Cross-platform** — Windows, Linux, macOS support

### Advanced Features

- **Token-based Auth** — Secure remote access
- **Session Management** — Multiple concurrent sessions
- **Output Buffering** — Configurable output history
- **Command History** — Track executed commands
- **Logging** — Comprehensive session and daemon logs
- **Stream-to-File** — Export terminal output to files

### AI Agent Integration

- **MCP Server** — Model Context Protocol server for AI agents (Claude Code, Cursor, Windsurf)
- **Universal tools** — Works in native shell, SSH, REPLs, interactive apps
- **Smart wait** — Commands wait for completion with configurable timeout
- **Special keys** — Ctrl+C, Ctrl+D, arrow keys, etc. for interactive apps

### Developer-Friendly

- **Python-first** — Easy to extend and integrate
- **PyPI Package** — Simple installation
- **Well-tested** — Comprehensive test suite
- **Configurable** — TOML-based configuration

---

## Architecture Summary

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLI       │     │   HTTP API  │     │  WebSocket  │
│  (silc)     │     │  (FastAPI)  │     │   Client    │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Daemon    │
                    │  (Manager)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
         │Session 1│  │Session 2│  │Session N│
         │ (PTY)   │  │ (PTY)   │  │ (PTY)   │
         └────┬────┘  └────┬────┘  └────┬────┘
              │            │            │
         ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
         │ Shell 1 │  │ Shell 2 │  │ Shell N │
         └─────────┘  └─────────┘  └─────────┘
```

**Components:**
- **Daemon** — Background process managing sessions (port 19999)
- **Session** — Independent shell with its own PTY (ports 20000+)
- **CLI** — Command-line interface for human interaction
- **API** — FastAPI server for programmatic access
- **TUI/Web UI** — Interactive interfaces

---

## User Flows

### Flow 1: Quick Command Execution

```bash
silc start                    # Start daemon and create session
silc 20000 run "ls -la"       # Execute command
silc 20000 out                # View output
```

### Flow 2: AI Agent Integration

```python
import requests

# Run command via API
response = requests.post("http://localhost:20000/run", json={
    "command": "git status",
    "timeout": 60
})
output = response.json()["output"]
```

### Flow 3: Interactive Development

```bash
silc start                    # Start session
silc 20000 tui                # Launch native TUI
# ... interactive work ...
```

### Flow 4: Remote Access

```bash
# On server
silc start --global --token <your-token>

# From client (via SSH tunnel)
ssh -L 20000:localhost:20000 user@server
silc 20000 run "htop"         # Use TUI apps remotely
```

---

## CLI Commands

### Daemon Management

| Command | Description |
|---------|-------------|
| `silc start [--port <n>] [--global] [--no-detach] [--token <t>]` | Start daemon (if not running) and create a new session |
| `silc list` | List all active sessions |
| `silc shutdown` | Gracefully shut down daemon and all sessions |
| `silc killall` | Force kill daemon and all sessions |
| `silc logs [--tail N]` | Show daemon logs |

### Session Commands

All session commands use the syntax `silc <port> <command>`.

| Command | Description |
|---------|-------------|
| `silc <port> run <command...>` | Execute a shell command |
| `silc <port> out [<lines>]` | Fetch latest terminal output |
| `silc <port> in <text...>` | Send raw input to the shell |
| `silc <port> status` | Show session status |
| `silc <port> interrupt` | Send Ctrl+C to the session |
| `silc <port> clear` | Clear the terminal screen |
| `silc <port> reset` | Reset terminal state |
| `silc <port> resize <rows> <cols>` | Resize terminal dimensions |
| `silc <port> close` | Gracefully close the session |
| `silc <port> kill` | Force kill the session |
| `silc <port> logs [--tail N]` | Show session logs |
| `silc <port> tui` | Launch native TUI client |
| `silc <port> web` | Open web UI in browser |

### Stream-to-File Commands

| Command | Description |
|---------|-------------|
| `silc <port> stream-render <filename> [--interval N]` | Stream rendered output to file |
| `silc <port> stream-append <filename> [--interval N]` | Append output to file with deduplication |
| `silc <port> stream-stop <filename>` | Stop streaming to file |
| `silc <port> stream-status` | Show streaming status |

### Command Options

#### `silc start`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--port` | int | auto | Specific port for session |
| `--global` | flag | false | Bind to 0.0.0.0 (network accessible) |
| `--no-detach` | flag | false | Run daemon in foreground |
| `--token` | string | auto | Custom API token for remote access |
| `--shell` | string | auto | Shell to use (bash, zsh, pwsh, cmd) |
| `--cwd` | string | daemon cwd | Working directory for session |

#### `silc <port> run`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--timeout` | int | 60 | Command timeout in seconds |

#### `silc <port> out`

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `lines` | int | 100 | Number of lines to fetch |

#### `silc <port> resize`

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `rows` | int | 24 | Number of rows |
| `cols` | int | 80 | Number of columns |

---

## REST API

The API is exposed by the FastAPI server. All endpoints (except `/web`) require a valid API token unless the client is connecting from localhost.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Return session status |
| `GET` | `/out?lines=N` | Return last N lines of terminal output |
| `GET` | `/raw?lines=N` | Return raw output (no rendering) |
| `GET` | `/logs?tail=N` | Return last N lines of session log |
| `GET` | `/stream` | Server-sent events stream of terminal output |
| `POST` | `/in` | Send raw input to the session |
| `POST` | `/run` | Execute a shell command |
| `POST` | `/interrupt` | Send Ctrl+C to the session |
| `POST` | `/clear` | Clear the terminal screen |
| `POST` | `/reset` | Reset terminal state |
| `POST` | `/resize` | Resize PTY dimensions |
| `POST` | `/close` | Gracefully close the session |
| `POST` | `/kill` | Force kill the session |
| `GET` | `/token` | Return the current session token |
| `GET` | `/web` | Serve the static web UI |

### Request/Response Schemas

#### `GET /status`

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

#### `GET /out`

**Query Parameters:**
- `lines` (int, default: 100) — Number of lines to return

**Response:**
```json
{
  "output": "Last N lines of terminal output...",
  "lines": 100
}
```

#### `POST /run`

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

**Response (success):**
```json
{
  "output": "total 42\ndrwxr-xr-x  5 user  staff   160 Jan 26 10:00 .",
  "exit_code": 0,
  "status": "completed"
}
```

**Response (timeout):**
```json
{
  "output": "Partial output...",
  "status": "timeout",
  "error": "Command did not complete in 60s"
}
```

**Response (busy):**
```json
{
  "error": "Another run command is already executing",
  "status": "busy",
  "running_cmd": "sleep 100"
}
```

**Response (buffer overflow):**
```json
{
  "output": "",
  "exit_code": -1,
  "status": "error",
  "error": "Command output exceeded 5242880 bytes limit"
}
```

#### `POST /in`

**Request Body:** Plain text (sent to shell)

**Query Parameters:**
- `nonewline` (bool, default: false) — Don't append newline

**Response:**
```json
{
  "status": "sent"
}
```

#### `POST /resize`

**Query Parameters:**
- `rows` (int, required) — Number of rows
- `cols` (int, required) — Number of columns

**Response:**
```json
{
  "status": "resized",
  "rows": 40,
  "cols": 120
}
```

### Authentication

For non-localhost connections, include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://remote-host:20000/status
```

Or as a query parameter:

```bash
curl http://remote-host:20000/status?token=YOUR_TOKEN
```

### Error Responses

All endpoints may return error responses:

```json
{
  "detail": "Error message"
}
```

**HTTP Status Codes:**
- `400` — Bad request (invalid parameters)
- `401` — Unauthorized (missing or invalid token)
- `403` — Forbidden (invalid token)
- `404` — Session not found
- `410` — Session has ended
- `500` — Internal server error

---

## Daemon API

The daemon exposes a management API on port 19999 for session lifecycle operations.

### Endpoints

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
  "port": null,
  "is_global": false,
  "token": null,
  "shell": "bash",
  "cwd": "/home/user/project"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `port` | int | auto | Desired port for session |
| `is_global` | bool | false | Bind to 0.0.0.0 (network accessible) |
| `token` | string | auto | Custom API token for remote access |
| `shell` | string | auto | Shell type (bash, zsh, pwsh, cmd, sh) |
| `cwd` | string | daemon cwd | Working directory for session |

**Response:**
```json
{
  "port": 20000,
  "session_id": "abc12345",
  "shell": "bash"
}
```

---

## MCP Server

SILC provides a Model Context Protocol (MCP) server for AI agent integration (Claude Code, Cursor, Windsurf, etc.).

### Tools

| Tool | Description |
|------|-------------|
| `send(port, text, timeout_ms)` | Send text to session, wait for output |
| `read(port, lines)` | Read current terminal output |
| `send_key(port, key)` | Send special keys (ctrl+c, enter, etc.) |
| `list_sessions()` | List all active sessions |
| `start_session(port?, shell?, cwd?)` | Create a new session |
| `close_session(port)` | Close a session |
| `get_status(port)` | Get session status |
| `run(port, command, timeout_ms)` | Execute command with exit code (native shell only) |

### Usage Example

```python
# Start a session
session = start_session()
# → { port: 20000, session_id: "abc12345" }

# Execute a command (waits up to 5s by default)
result = send(20000, "ls -la")
# → { output: "total 42\ndrwxr-xr-x...", lines: 15, alive: true }

# Interactive app - fire and forget
send(20000, "htop", timeout_ms=0)

# Read current screen
read(20000, lines=40)

# Quit htop
send_key(20000, "q")

# SSH flow - works in remote shell too
send(20000, "ssh user@remote", timeout_ms=10000)
send(20000, "df -h", timeout_ms=5000)
```

### Key Design

- **`send` always waits** (default 5s) — returns output captured during wait
- **`timeout_ms=0`** — fire-and-forget mode, returns immediately
- **Universal** — works in native shell, SSH, Python REPL, htop, any interactive context
- **`run` is convenience only** — uses sentinel wrapper, only works in native shell

---

## WebSocket API

Connect to `ws://localhost:<port>/ws` for real-time terminal output.

### Connection

```text
ws://localhost:20000/ws?token=YOUR_TOKEN
```

Token is required for non-localhost connections.

### Server Messages

**Output update:**
```json
{
  "event": "update",
  "data": "terminal output text..."
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

---

## Configuration

Configuration is loaded from (highest to lowest priority):
1. Environment variables (`SILC_*`)
2. Configuration file (`silc.toml`)
3. Default values

### Configuration File Location

- **Linux/macOS**: `~/.silc/silc.toml`
- **Windows**: `%APPDATA%\silc\silc.toml`

### Configuration Options

#### `[ports]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `daemon_start` | int | 19999 | Starting port for daemon |
| `daemon_end` | int | 20000 | Ending port for daemon |
| `session_start` | int | 20000 | Starting port for sessions |
| `session_end` | int | 21000 | Ending port for sessions |
| `max_attempts` | int | 10 | Max ports to try when finding available port |

**Environment Variables:** `SILC_DAEMON_PORT_START`, `SILC_DAEMON_PORT_END`, `SILC_SESSION_PORT_START`, `SILC_SESSION_PORT_END`, `SILC_PORT_MAX_ATTEMPTS`

#### `[paths]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `data_dir` | string | `~/.silc` | Data directory for SILC |
| `log_dir` | string | `<data_dir>/logs` | Log directory |

**Environment Variables:** `SILC_DATA_DIR`, `SILC_LOG_DIR`

#### `[tls]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable TLS/SSL |
| `cert_path` | string | null | Path to TLS certificate |
| `key_path` | string | null | Path to TLS private key |

**Environment Variables:** `SILC_TLS_ENABLED`, `SILC_TLS_CERT_PATH`, `SILC_TLS_KEY_PATH`

#### `[tokens]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `length` | int | 32 | Length of generated API tokens |
| `require_token` | bool | true | Require token for non-localhost |

**Environment Variables:** `SILC_TOKEN_LENGTH`, `SILC_REQUIRE_TOKEN`

#### `[sessions]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_timeout` | int | 600 | Default command timeout (seconds) |
| `max_buffer_bytes` | int | 5242880 | Maximum buffer size (5MB) |
| `idle_timeout` | int | 1800 | Session idle timeout (seconds) |
| `gc_interval` | int | 60 | Garbage collection interval (seconds) |

**Environment Variables:** `SILC_COMMAND_TIMEOUT`, `SILC_MAX_BUFFER_BYTES`, `SILC_IDLE_TIMEOUT`, `SILC_GC_INTERVAL`

#### `[logging]`

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_log_lines` | int | 1000 | Maximum lines in log files |
| `log_level` | string | INFO | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

**Environment Variables:** `SILC_MAX_LOG_LINES`, `SILC_LOG_LEVEL`

---

## Behavior Guarantees

### Session Lifecycle

| Guarantee | Description |
|-----------|-------------|
| **Auto-start daemon** | `silc start` starts daemon if not running |
| **Auto-create session** | `silc start` creates first session automatically |
| **Idle cleanup** | Sessions idle > 30 minutes are garbage collected |
| **Graceful shutdown** | `silc shutdown` closes all sessions cleanly |
| **Force kill** | `silc killall` terminates everything immediately |

### Command Execution

| Guarantee | Description |
|-----------|-------------|
| **Sentinel detection** | Commands use sentinel markers for reliable output capture |
| **Timeout enforcement** | Commands exceeding timeout are interrupted |
| **Buffer overflow protection** | Commands exceeding 5MB output are interrupted |
| **Lock protection** | Concurrent `run` requests return `busy` status |
| **Exit code capture** | Shell exit codes are captured and returned |

### Output Handling

| Guarantee | Description |
|-----------|-------------|
| **Ring buffer** | Output stored in configurable ring buffer (default 5MB) |
| **ANSI cleaning** | ANSI escape codes are cleaned from output |
| **Sentinel removal** | Internal sentinel markers are hidden from output |
| **Rendered view** | `/out` returns rendered terminal view (like TUI) |
| **Raw view** | `/raw` returns unprocessed output |

### Security

| Guarantee | Description |
|-----------|-------------|
| **Localhost bypass** | Localhost connections don't require token |
| **Token required for remote** | Non-localhost connections require valid token |
| **Token in header or query** | Token accepted via `Authorization` header or `?token=` query |
| **Real shell access** | Commands run with user's permissions |

---

## Edge Cases

### Port Conflicts

- If requested port is in use, session creation fails with error
- Use `silc start` without `--port` to auto-select available port
- Port range is configurable via `silc.toml`

### Session Not Responding

- Use `silc <port> interrupt` to send Ctrl+C
- Use `silc <port> kill` to force terminate
- Use `silc killall` as last resort

### Daemon Not Starting

- Check if daemon is already running: `silc list`
- Check daemon logs: `silc logs`
- Force kill existing: `silc killall`
- Retry: `silc start`

### Command Timeout

- Default timeout is 60 seconds (CLI) or 600 seconds (config)
- Override with `--timeout` flag
- Timeout returns partial output with `status: "timeout"`

### Buffer Overflow

- Commands producing > 5MB output are interrupted
- Returns `status: "error"` with overflow message
- Increase `max_buffer_bytes` in config if needed

### Concurrent Commands

- Only one `run` command can execute at a time per session
- Concurrent requests return `status: "busy"` with running command
- Use separate sessions for parallel execution

---

## Non-Goals

SILC deliberately does NOT:

- **Provide encryption by default** — TLS is opt-in, requires certificates
- **Persist sessions across reboots** — Sessions are ephemeral
- **Support multi-user authentication** — Single token per session
- **Replace tmux/screen** — Different use case (API access vs. multiplexing)
- **Provide shell isolation** — Commands run in user's shell environment

---

## Unresolved Questions

- **TLS implementation** — Currently experimental, needs real-world testing
- **Token expiration** — Tokens don't expire; rotation is manual
- **Rate limiting** — No built-in rate limiting for API endpoints
- **Audit logging** — No audit trail for security-sensitive operations

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `silc start` | Start daemon and create session |
| `silc <port> run "<cmd>"` | Execute command |
| `silc <port> out` | View output |
| `silc <port> status` | Check session status |
| `silc <port> tui` | Launch TUI |
| `silc list` | List all sessions |
| `silc shutdown` | Stop daemon |
| `silc killall` | Force kill everything |

| Port | Purpose |
|------|---------|
| 19999 | Daemon management API |
| 20000-21000 | Session ports (default range) |

| File | Purpose |
|------|---------|
| `~/.silc/silc.toml` | Configuration file |
| `~/.silc/logs/daemon.log` | Daemon log |
| `~/.silc/logs/session_<port>.log` | Session log |
