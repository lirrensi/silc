ARCH.md
 Architecture Documentation – Shared Interactive Linked CMD (SILC)
> **Shared Interactive Linked CMD (SILC)** bridges a terminal session with an HTTP API, enabling both humans and agents to read, write, and orchestrate commands in the same shell.
---
 Table of Contents
1. [Project Overview](#1-project-overview)  
2. [Core Technology Stack](#2-core-technology-stack)  
3. [High‑Level Architecture](#3-high‑level-architecture)  
4. [Package Structure](#4-package-structure)  
5. [Session Lifecycle](#5-session-lifecycle)  
6. [Daemon & Session Management](#6-daemon--session-management)  
7. [API Surface](#7-api-surface)  
8. [Textual UI](#8-textual-ui)  
9. [Persistence & Logging](#9-persistence--logging)  
10. [Security & Hard‑Exits](#10-security--hard-exits)  
11. [Testing Strategy](#11-testing-strategy)  
12. [CI / Build](#12-ci--build)  
13. [Future Work](#13-future-work)  
---
 1. Project Overview
SILC is a **Python‑first CLI and FastAPI service** that manages terminal sessions and a Textual TUI.
- **Purpose**: Allow users and automated agents to run shell commands, inspect output, and control terminal state over HTTP or a local CLI.
- **Users**: Developers, automation engineers, and anyone needing a programmatic shell interface.
- **Key Features**
  - Persistent, isolated shell sessions per port.
  - Automatic helper injection to capture command output cleanly.
  - Garbage collection of idle sessions.
  - Optional “global” mode exposing sessions over the network (RCE risk).
  - Textual TUI for interactive use.
  - Docker support for sandboxed execution.
---
 2. Core Technology Stack
| Layer | Library / Tool | Version (as in `pyproject.toml`) |
|-------|----------------|----------------------------------|
| Runtime | Python | ≥ 3.10 |
| CLI | `click` | ≥ 8.1.7 |
| Server | `FastAPI` | ≥ 0.104.0 |
| ASGI Server | `uvicorn[standard]` | ≥ 0.24.0 |
| PTY Handling | `psutil`, `pyte`, `pywinpty` | `psutil` ≥ 5.9.6, `pyte` ≥ 0.8.0, `pywinpty` ≥ 3.0.2 |
| HTTP Requests | `requests` | ≥ 2.31.0 |
| TUI | `textual` | ≥ 0.44.0 |
| Testing | `pytest`, `pytest‑asyncio` | `pytest` ≥ 9.0.2, `pytest‑asyncio` ≥ 1.3.0 |
> **Note** – All dependencies are pinned in `pyproject.toml` and installed via `pip install -e .[test]`.
---
 3. High‑Level Architecture
graph TD
    subgraph Client
        CLI[CLI] -->|CLI Commands| SILC[SilcDaemon]
        TUI[TUI] -->|WebSocket| SILC
    end
    subgraph Server
        SILC -->|FastAPI| SessionAPI[Session API]
        SessionAPI -->|CRUD| SessionMgr[Session Manager]
        SessionMgr -->|Session| Session[SilcSession]
        Session --> PTY[PTY]
        PTY -->|Buffer| Buffer[RawByteBuffer]
    end
    subgraph Persistence
        Log[Session Logs] -->|File| Persistence[Persistence Module]
    end
- Client  
  - CLI (silc command) or Textual TUI (silc <port> open).
- Daemon (SilcDaemon)  
  - Runs as a long‑lived FastAPI server on DAEMON_PORT (19999).  
  - Manages a registry of active sessions and their sockets.
- Session (SilcSession)  
  - Encapsulates a PTY, buffer, and rendering state.  
  - Provides run_command, get_output, resize, interrupt, clear_buffer, close, etc.
- Persistence  
  - Log files (DAEMON_LOG, per‑session logs) and PID file for daemon management.
---
4. Package Structure
silc/
├── __init__.py
├── __main__.py          # CLI entry point
├── api/                 # FastAPI route handlers
│   ├── __init__.py
│   ├── models.py
│   └── server.py
├── core/                # Session orchestration
│   ├── __init__.py
│   ├── session.py
│   ├── pty_manager.py
│   ├── raw_buffer.py
│   ├── cleaner.py
│   └── __pycache__/
├── daemon/              # Daemon process logic
│   ├── __init__.py
│   ├── manager.py
│   ├── pidfile.py
│   ├── registry.py
│   └── __pycache__/
├── tui/                 # Textual UI
│   ├── __init__.py
│   └── app.py
└── utils/               # Helpers
    ├── __init__.py
    ├── persistence.py
    ├── ports.py
    └── shell_detect.py
- __main__.py – Parses CLI options and delegates to silc.__main__ functions.
- api.server – Creates a FastAPI app for session APIs (/sessions, /sessions/{port}, /shutdown, /killall, etc.).
- core.session – Core logic: PTY management, helper injection, output rendering, garbage collection.
- daemon.manager – Orchestrates multiple sessions, starts/stops servers, handles cleanup.
- tui.app – Textual UI that connects to a session via WebSocket.
- utils.persistence – Log rotation, session log handling, PID file utilities.
---
5. Session Lifecycle
| Step | Description | Key Code |
|------|-------------|----------|
| Create | silc start --port <n> → Daemon creates a SilcSession. | daemon.manager.SilcDaemon._create_session_server |
| Helper Injection | Injects shell helper function to capture sentinel markers. | core.session.SilcSession._inject_helper |
| Run Command | silc <port> run <cmd> → writes command via PTY, waits for sentinel markers, collects output. | core.session.SilcSession.run_command |
| Output | silc <port> out → fetches latest buffer or rendered screen. | core.session.SilcSession.get_output |
| Resize | silc <port> resize <rows> <cols> | core.session.SilcSession.resize |
| Interrupt | silc <port> interrupt (Ctrl‑C). | core.session.SilcSession.interrupt |
| Close | silc <port> close or daemon shutdown. | core.session.SilcSession.close |
| GC | Idle >30 min → auto‑close. | core.session.SilcSession._garbage_collect and daemon.manager.SilcDaemon._garbage_collect |
---
6. Daemon & Session Management
- PID File – Ensures only one daemon per machine (daemon.pidfile).
- Session Registry – daemon.registry.SessionRegistry tracks port → session_id → shell_type.
- Socket Binding – utils.ports.bind_port reserves a TCP port for the session’s HTTP server.
- Cleanup – On session close or daemon shutdown, the daemon:
  1. Stops the per‑session Uvicorn server.
  2. Cancels the PTY read task.
  3. Terminates orphaned shell processes listening on the session port.
  4. Removes registry entry and deletes session logs.
---
7. API Surface
| Endpoint | Method | Purpose |
|----------|--------|---------|
| /sessions | POST | Create a new session (returns port, session_id, shell). |
| /sessions | GET | List active sessions. |
| /sessions/{port} | DELETE | Close a specific session. |
| /shutdown | POST | Graceful shutdown of daemon. |
| /killall | POST | Force‑kill all sessions and daemon. |
| /sessions/{port}/out | GET | Get latest session output. |
| /sessions/{port}/in | POST | Send raw input. |
| /sessions/{port}/run | POST | Execute command. |
| /sessions/{port}/status | GET | Session status. |
| /sessions/{port}/clear | POST | Clear buffer. |
| /sessions/{port}/interrupt | POST | Send Ctrl‑C. |
| /sessions/{port}/resize | POST | Resize terminal. |
| /sessions/{port}/logs | GET | Session logs. |
> The API is generated by api.server.create_app(session) and wrapped by FastAPI.
---
8. Textual UI
- Entry point: silc <port> open.
- Connects to the session’s WebSocket endpoint (/sessions/{port}/websocket internally).
- Renders live terminal output using pyte rendering pipeline.
- Allows interactive input, resizing, and interrupt.
---
9. Persistence & Logging
| File | Purpose |
|------|---------|
| utils.persistence.DAEMON_LOG | Central daemon log (silc.log). |
| utils.persistence.LOGS_DIR | Directory for per‑session logs (session_<port>.log). |
| utils.persistence.rotate_session_log(port, max_lines=1000) | Rotates logs to keep size manageable. |
| utils.persistence.write_daemon_log(msg) | Append message to daemon log. |
| utils.persistence.write_session_log(port, msg) | Append message to session log. |
| utils.persistence.cleanup_session_log(port) | Delete session log on shutdown. |
---
10. Security & Hard‑Exits
- Global Binding (--global) exposes a session on 0.0.0.0. The CLI warns of RCE risk.  
- Hard‑Exit Watchdog (_hard_exit_after) terminates the process if uvicorn/asyncio hangs, especially on Windows.  
- PID File prevents multiple daemons and accidental re‑starts.  
- Process Killing (daemon.manager.SilcDaemon._kill_processes_on_port_sync) only targets shell processes listening on the session port.
---
11. Testing Strategy
- Unit Tests – tests/*.py cover core utilities and session logic.  
- Integration Tests – tests/test_daemon.py, tests/test_session.py exercise full lifecycle.  
- Manual Tests – manual_tests/ scripts for interactive scenarios.  
- Run: pytest tests/ (requires [test] extras).  
> All tests use pytest‑asyncio for async fixtures.
---
12. CI / Build
- CI – GitHub Actions (not shipped with the repo). Typical workflow:
    - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: python-version: '3.11'
  - run: pip install -e .[test]
  - run: pre-commit run --all-files
  - run: pytest tests/
  - Build – build.py creates an executable with PyInstaller.  
- Docker – docker-compose.yml builds a container running the daemon.
---
13. Future Work
- Web UI – Add a browser‑based terminal emulator.  
- Authentication – Basic token or OAuth support for the API.  
- Metrics – Prometheus exporter for session metrics.  
- Extensible Helpers – Allow custom helper injection per shell.  
- Improved GC – Fine‑grained idle thresholds and user‑configurable.  
---
Appendix – Key Files
| Path | Purpose | Note |
|------|---------|------|
| silc/__main__.py | CLI entry point | Parses silc start and port sub‑commands |
| silc/api/server.py | FastAPI app factory | Exposes /sessions endpoints |
| silc/core/session.py | Session orchestration | Main PTY logic |
| silc/daemon/manager.py | Daemon lifecycle | Handles session servers and cleanup |
| silc/utils/persistence.py | Log/PID helpers | Centralized persistence |
| silc/utils/ports.py | Port binding helpers | bind_port, find_available_port |
| silc/utils/shell_detect.py | Detects current shell | Determines helper injection logic |