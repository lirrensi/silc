# Future Work Proposals

- **Session Locking & Queueing** – Implement a token‑based lock system so that concurrent `run` requests are queued instead of failing with *busy*.
=> currently two same run may break everything!
=> add a lock - when one /run commands present =>
this may prevent errors on sync runs, but its not preventing 2 `/in` as same time, which we cant really detect;
[DONE] => on lock => error + which command;

- **Enhanced Logging** – Persist each session’s stdout/stderr to a rotating log file and expose `/logs` endpoint.
=> add logs + /logs command `slic 2222 logs` to see internal logs easy
also silc logs => outputs daemon logs directly
[DONE] =>
Persistence module (silc/utils/persistence.py):
- Added write_session_log(port, message) - Append to session log file
- Added rotate_session_log(port, max_lines=1000) - Keep only last N lines
- Added read_session_log(port, tail_lines=None) - Read session logs
Session module (silc/core/session.py):
- Integrated logging in _read_loop to capture PTY stdout/stderr
- Added command logging in run_command to track executed commands
- Added rotate_logs() method to rotate session logs periodically
- Periodic log rotation in _garbage_collect (every 60s)
API server (silc/api/server.py):
- Added GET /logs?tail=N endpoint to retrieve session logs
CLI (silc/__main__.py):
- Added silc logs [--tail N] - Show daemon logs
- Added silc <port> logs [--tail N] - Show session logs
Log storage: ~/silc/logs/ (or %APPDATA%\silc\logs\ on Windows)
- daemon.log - Daemon activity
- session_<port>.log - Per-session stdout/stderr with commands
All logs automatically rotate to keep maximum 1000 lines as requested.


- **Graceful Termination** – Add support for SIGTERM/SIGINT handling in the daemon to clean up orphaned PTYs.
=> we probably have it with shutdown | killall, but check again?
[DONE] => 
Let me verify the fix makes sense:
1. Signal handler sets _shutdown_event
2. _watch_shutdown task is waiting on this event
3. When triggered, it now iterates through all sessions and calls _ensure_cleanup_task(port) with timeout
4. This is the same logic as the /shutdown endpoint
This should properly clean up orphaned PTYs when SIGTERM/SIGINT is received.
Fixed. The _watch_shutdown method now properly cleans up all sessions when the shutdown event is set (triggered by SIGTERM/SIGINT), mirroring the /shutdown endpoint logic.


- **Configuration File** – Allow users to override defaults (port ranges, log paths) via a `silc.toml`.
=> add ability to change default daemon port
=> [DONE] (2025-01-26)
Implemented comprehensive configuration system:
- Created silc/config.py with full configuration support
- Configuration sources: silc.toml file, environment variables (SILC_*), defaults
- Configurable options:
  - Port ranges (daemon start/end, session start/end, max attempts)
  - Paths (data directory, log directory)
  - TLS settings (enabled, cert path, key path)
  - Token settings (length, require token)
  - Session settings (timeout, buffer size, idle timeout, GC interval)
  - Logging settings (max log lines, log level)
- Updated silc/utils/ports.py to use config for port ranges
- Updated silc/utils/persistence.py to use config for paths and log settings
- Created docs/silc.toml.example with example configuration
- Created docs/configuration.md with comprehensive documentation
- Added configuration section to README.md

- **Security**
=> check how --global works now;
`silc start -port 2222 --global => pins to 0.0.0.0 instead of 127
Also make a big red warning that this is RCE risk
[DONE] => 
Changes made:
1. CLI (silc/__main__.py:234-252):
   - Added prominent red/bold warnings when --global is used
   - Explicit RCE risk warning
   - Firewall recommendation message
   - Passes is_global to daemon in session creation payload
2. Daemon Manager (silc/daemon/manager.py):
   - Added is_global: bool = False to SessionCreateRequest model (line 59)
   - Modified session creation to use is_global flag (lines 98-101)
   - Updated _create_session_server to bind to 0.0.0.0 when is_global=True (line 286)
   - Updated _reserve_session_socket to bind to 0.0.0.0 when is_global=True (line 326)
   - Added daemon log warning for globally accessible sessions (lines 130-133)
3. Daemon stays local: The daemon API server still binds to 127.0.0.1:19999 (unchanged)
Usage:
silc start --port 2222 --global
This now:
- Shows big red RCE warnings
- Binds the session server to 0.0.0.0:2222 (network accessible)
- Keeps daemon local at 127.0.0.1:19999


- **Dependency Isolation** – Package the CLI as a Docker image for easy distribution.
=> just make a docker compose yaml just in case anyone wants, but that kinda defeats the purpose of everything?
=> but still useful to give agent basically a full docker space control to do whatever
(not sure it would work tho?)
=> Done! Created:
- docker-compose.yml - Run SILC daemon in Docker
- Dockerfile - Minimal Python 3.11 image
- .dockerignore - Smaller builds
- Updated README.md - Added "Docker mode" section
The README explains this as a sandboxed/API-first use case, noting the tradeoff: no access to host files/environment (intentional isolation).


[DONE] (2025-01-26)
- **Documentation** – Update `docs/` with usage examples, architecture diagram, and troubleshooting guide.
=> also readme with all commands + potentially update full list of commands for easy management;
Completed:
- Updated README.md with real repository URL (https://github.com/lirrensi/silc)
- Added configuration section to README.md
- Updated docs/commands_and_api.md with real TUI repository URL (lirrensi/silc)
- Added comprehensive API examples with request/response samples
- Added authentication examples
- Added error code documentation
- Created docs/configuration.md with complete configuration reference
- Created docs/architecture.md with system architecture diagram
- Created docs/silc.toml.example with example configuration file