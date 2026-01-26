# SILC Architecture

This document describes the architecture and design of SILC (Shared Interactive Linked CMD).

## Overview

SILC is a Python-based system that bridges interactive terminal sessions with HTTP APIs, enabling both humans and agents to interact with the same shell session.

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

## Components

### 1. CLI (`silc/__main__.py`)

The command-line interface provides user-friendly commands to interact with SILC.

**Key Features:**
- Command parsing and validation
- HTTP client for daemon communication
- Session management commands
- Output formatting

**Main Commands:**
- `silc start` - Start daemon and create session
- `silc create` - Create new session
- `silc <port> run` - Execute command
- `silc <port> out` - Get output
- `silc list` - List sessions
- `silc shutdown` - Stop daemon

### 2. Daemon (`silc/daemon/`)

The daemon manages the lifecycle of sessions and provides the HTTP API.

**Components:**
- **Manager** (`manager.py`) - Main daemon process
- **Registry** (`registry.py`) - Session registry and lookup
- **PID File** (`pidfile.py`) - Daemon process tracking

**Responsibilities:**
- Session lifecycle management
- HTTP server hosting
- Session garbage collection
- Process monitoring

### 3. Session (`silc/core/`)

Each session represents an interactive shell with PTY (pseudo-terminal).

**Components:**
- **Session** (`session.py`) - Main session logic
- **PTY Manager** (`pty_manager.py`) - PTY creation and management
- **Raw Buffer** (`raw_buffer.py`) - Output buffering
- **Cleaner** (`cleaner.py`) - Output cleaning (ANSI codes, etc.)

**Key Features:**
- PTY creation (platform-specific)
- Command execution with sentinel detection
- Output buffering and cleaning
- Session state management

### 4. API Server (`silc/api/`)

FastAPI-based HTTP API for programmatic access.

**Components:**
- **Server** (`server.py`) - FastAPI application
- **Models** (`models.py`) - Pydantic models for request/response

**Endpoints:**
- `/status` - Session status
- `/run` - Execute command
- `/out` - Get output
- `/in` - Send input
- `/resize` - Resize terminal
- `/interrupt` - Interrupt command
- `/clear` - Clear buffer
- `/close` - Close session
- `/ws` - WebSocket connection

### 5. TUI (`silc/tui/`)

Textual-based terminal user interface for interactive sessions.

**Components:**
- **App** (`app.py`) - Textual application
- **Installer** (`installer.py`) - TUI binary installer

### 6. Utilities (`silc/utils/`)

Shared utility modules.

**Components:**
- **Persistence** (`persistence.py`) - Data directory and logging
- **Ports** (`ports.py`) - Port management
- **Shell Detect** (`shell_detect.py`) - Shell detection
- **Config** (`config.py`) - Configuration management

## Data Flow

### Command Execution Flow

```
1. CLI: silc 20000 run "ls -la"
   ↓
2. CLI sends HTTP POST to http://localhost:20000/run
   ↓
3. API Server receives request
   ↓
4. API Server validates token (if not localhost)
   ↓
5. API Server calls session.run_command("ls -la")
   ↓
6. Session sends command to PTY
   ↓
7. PTY executes in shell
   ↓
8. Session reads output until sentinel
   ↓
9. Session returns output to API Server
   ↓
10. API Server returns JSON response to CLI
   ↓
11. CLI displays output to user
```

### WebSocket Flow

```
1. Client connects to ws://localhost:20000/ws?token=TOKEN
   ↓
2. API Server validates token
   ↓
3. WebSocket connection established
   ↓
4. Session sends output updates to WebSocket
   ↓
5. Client receives real-time output
   ↓
6. Client can send input via WebSocket
   ↓
7. Session forwards input to PTY
```

## Platform Support

### Windows
- Uses `pywinpty` for PTY creation
- PTY Manager loads winpty module
- Data directory: `%APPDATA%\silc`

### Linux/macOS
- Uses standard `pty` module
- PTY Manager uses `pty.fork()`
- Data directory: `~/.silc`

## Configuration

Configuration is loaded from:
1. `silc.toml` file in data directory
2. Environment variables (`SILC_*`)
3. Default values

See [configuration.md](configuration.md) for details.

## Security Model

### Authentication
- API tokens required for non-localhost connections
- Tokens generated per session
- Token validation on each request

### Authorization
- Localhost connections bypass token check
- Remote connections require valid token
- Token can be obtained via `/token` endpoint

### Security Considerations
- ⚠️ Tokens sent over plaintext HTTP by default
- ⚠️ `--global` flag exposes sessions to all interfaces
- ⚠️ Real shell access with user permissions
- TLS support available but not enabled by default

See [README.md](../README.md#security-considerations) for security best practices.

## Performance Considerations

### Buffer Management
- Output buffered in memory (configurable limit: 5MB default)
- Commands exceeding buffer limit are interrupted
- Log rotation to prevent disk space issues

### Session Management
- Idle sessions garbage collected (30 min default)
- Session state tracked in memory
- PID files for daemon tracking

### Concurrency
- Async/await for I/O operations
- Multiple sessions can run concurrently
- Thread-safe session registry

## Error Handling

### Session Errors
- PTY creation failures
- Command execution timeouts
- Buffer overflow
- Shell termination

### API Errors
- Invalid tokens
- Missing sessions
- Invalid parameters
- Internal errors

### CLI Errors
- Daemon not running
- Session not found
- Port conflicts
- Connection failures

## Logging

### Daemon Log
- Location: `<data_dir>/logs/daemon.log`
- Contains daemon lifecycle events
- Rotated to 1000 lines by default

### Session Logs
- Location: `<data_dir>/logs/session_<port>.log`
- Contains session-specific events
- Rotated to 1000 lines by default

## Testing

### Unit Tests
- Session lifecycle
- PTY management
- Output cleaning
- Buffer management

### Integration Tests
- API endpoints
- CLI commands
- Daemon management
- Multi-session scenarios

### Test Tools
- `pytest` for test framework
- `pytest-asyncio` for async tests
- `httpx.AsyncClient` for API testing

## Future Enhancements

### Planned Features
- TLS/WSS support for secure connections
- Output streaming for long-running commands
- Configuration file support ✅ (implemented)
- Enhanced logging and monitoring
- Session templates
- Command history

### Performance Improvements
- Optimized log rotation (tail-based)
- HTTP connection pooling
- Async file I/O
- Output streaming

### Security Enhancements
- Rate limiting
- Token expiration
- Enhanced authentication
- Audit logging

## Dependencies

### Core Dependencies
- `fastapi` - HTTP API framework
- `uvicorn` - ASGI server
- `textual` - TUI framework
- `click` - CLI framework
- `psutil` - Process management
- `requests` - HTTP client
- `websockets` - WebSocket support
- `httpx` - Async HTTP client
- `toml` - Configuration parsing

### Platform Dependencies
- `pywinpty` - Windows PTY support

### Development Dependencies
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `black` - Code formatting
- `mypy` - Type checking

## Contributing

See [AGENTS.md](../AGENTS.md) for development guidelines and coding standards.

## License

See LICENSE file for details.