# daemon.md

## SILC Daemon Architecture

The daemon is the central process that manages multiple shell sessions. It exposes a FastAPI **API** on port `DAEMON_PORT` (19999) and launches a dedicated Uvicorn server for each session.

### Key Components

- **`SilcDaemon`** – Orchestrates the life‑cycle of all sessions.  It creates a per‑session Uvicorn server, starts a background task that performs garbage collection, and watches for shutdown signals.
- **`SessionRegistry`** – Keeps a mapping of `port → session_id → shell_type`.  The registry is consulted when listing sessions or cleaning up.
- **`PID File`** – `daemon.pidfile` protects against multiple daemons.  It is written on start and removed on shutdown.
- **`Per‑session Uvicorn Server`** – Each session gets its own server bound to `127.0.0.1` (or `0.0.0.0` if `--global`).  The server hosts the session’s FastAPI endpoints (`/out`, `/run`, etc.).
- **`Session Cleanup`** – On session close or daemon shutdown the daemon:
  1. Stops the per‑session server.
  2. Cancels the PTY read task.
  3. Calls `kill_processes_on_port` to terminate any orphaned shell.
  4. Removes the registry entry and deletes session logs.

### Flow
1. **Start Daemon** (`silc start` without `--global`):
   - Daemon writes PID file.
   - Creates a FastAPI app via `create_app`.
   - Listens on `DAEMON_PORT`.
2. **Create Session** (`silc start --port 20000`):
   - Daemon reserves a free TCP port for the session.
   - Calls `create_session` endpoint → new `SilcSession`.
   - Launches a second Uvicorn server on the session port.
3. **API Calls** – Clients hit the session server for commands.
4. **Shutdown** – `silc shutdown` or `silc killall` triggers graceful or forced cleanup.

### Notes
- The daemon uses a watchdog (`_hard_exit_after`) to terminate itself if Uvicorn hangs.
- The daemon logs all lifecycle events to `DAEMON_LOG`.

---

