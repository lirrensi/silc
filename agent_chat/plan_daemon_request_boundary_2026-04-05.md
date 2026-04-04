# Plan: Daemon Request Failure Boundary
_Done means no daemon API request can crash the daemon process; non-shutdown failures are logged with traceback details and returned as structured HTTP error responses._

---

# Checklist
- [ ] Step 1: Add shared daemon error formatting and traceback logging helpers
- [ ] Step 2: Install daemon-wide FastAPI exception handlers
- [ ] Step 3: Wrap create-session and daemon control endpoints with explicit failure boundaries
- [ ] Step 4: Harden daemon background tasks and startup watchers against unhandled exceptions
- [ ] Step 5: Harden resurrect and restart flows so bad session state is quarantined instead of crashing the daemon
- [ ] Step 6: Update architecture docs for daemon request-failure boundaries
- [ ] Step 7: Run focused verification that failed requests return errors without killing the daemon

---

## Context
- The daemon API lives in `silc/daemon/manager.py`.
- Per-session HTTP and websocket APIs live in `silc/api/server.py`.
- The daemon currently creates the FastAPI app inside `SilcDaemon._create_daemon_api()`.
- Session creation is implemented by the nested `create_session()` route in `SilcDaemon._create_daemon_api()`.
- Session resurrection is implemented by `SilcDaemon._resurrect_sessions()`.
- Background session server failure handling is implemented by `SilcDaemon._attach_session_task()` and `SilcDaemon._handle_session_task_done()`.
- HTTP server restart watching is implemented by `SilcDaemon._watch_restart()`.
- Startup is implemented by `SilcDaemon.start()`.
- Architecture documentation for the API server lives in `docs/arch_api.md`.

## Prerequisites
- Repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- Use the project virtual environment Python at `C:\Users\rx\001_Code\100_M\SILC\.venv\Scripts\python.exe` for any verification commands.
- Do not run the full test suite. Use targeted checks only.
- If the daemon is already running before verification, stop it with `python -m silc killall` from the project virtual environment before starting targeted checks.

## Scope Boundaries
- Do not change the websocket binary framing protocol in `silc/api/server.py`.
- Do not change the manager web UI files under `manager_web_ui/` in this plan.
- Do not change the Rust TUI client in `tui_client/` in this plan.
- Do not redesign session persistence format in `silc/utils/persistence.py` beyond minimal read-side quarantine handling required by this plan.
- Do not change shutdown or killall semantics except to preserve their expected process-exit behavior.

---

## Steps

### Step 1: Add shared daemon error formatting and traceback logging helpers
Open `silc/daemon/manager.py`.

Add small helper functions or methods near the top of the module that do all of the following:
1. Capture a full traceback string for an exception.
2. Write a single-line daemon log summary with an operation label and exception message.
3. Write the traceback string to the daemon log in a readable multi-line form.
4. Build a structured JSON-safe error response payload with these keys:
   - `error`: short stable external message
   - `detail`: exact exception message string
   - `operation`: daemon operation label such as `create_session` or `restart_server`
   - `traceback`: full traceback string

The helper must keep internal logic centralized so later steps do not duplicate traceback formatting inline.

✅ Success: `silc/daemon/manager.py` contains reusable helpers that can log a traceback and build a structured error payload from an exception plus operation label.
❌ If failed: revert the newly added helper code in `silc/daemon/manager.py` and stop. Do not continue with duplicated per-route traceback formatting.

### Step 2: Install daemon-wide FastAPI exception handlers
Open `silc/daemon/manager.py` and modify `SilcDaemon._create_daemon_api()`.

Register explicit FastAPI exception handlers on the daemon app for:
1. `HTTPException`
2. generic `Exception`

Implement these exact rules:
1. `HTTPException` must return a JSON response and must not crash the daemon.
2. If an `HTTPException.detail` is already a dictionary, return it unchanged as the JSON body.
3. If an `HTTPException.detail` is a string, return `{"error": <detail>}` as the JSON body.
4. The generic `Exception` handler must use the Step 1 helper to log the full traceback and return HTTP 500 with the structured error payload.
5. The generic `Exception` handler must never re-raise.

Use FastAPI/Starlette JSON response objects directly. Do not rely on default exception pages.

✅ Success: daemon API routes now always terminate in a JSON response for both `HTTPException` and unexpected exceptions, and unexpected exceptions are logged with traceback details.
❌ If failed: remove the new exception handlers and stop. Do not continue with partially-installed error boundaries.

### Step 3: Wrap create-session and daemon control endpoints with explicit failure boundaries
Open `silc/daemon/manager.py` and modify the nested routes inside `SilcDaemon._create_daemon_api()`.

For each of these routes, add an explicit outer `try/except` boundary that catches non-`HTTPException` exceptions, logs with the Step 1 helper, and raises `HTTPException(status_code=500, detail=<structured payload>)`:
1. `create_session()`
2. `list_sessions()`
3. `get_defaults()`
4. `resolve_session()`
5. `close_session()`
6. `kill_session()`
7. `restart_session()`
8. `restart_server()`
9. `resurrect()`

Within `create_session()`, make these exact containment rules:
1. If `_reserve_session_socket()` succeeds and any later step fails, always close the reserved socket.
2. If `SilcSession(...)` construction or `await session.start()` fails, do not leave anything in `self.sessions`, `self.servers`, `self._session_tasks`, or `self.registry` for that port.
3. Return structured HTTP 400 only for user-caused validation problems such as bad name, unknown shell, duplicate port, duplicate name, or exhausted session limit.
4. Return structured HTTP 500 for all other failures, including PTY spawn failures and shell startup failures.

Within `restart_session()`, keep shutdown semantics unchanged but ensure all non-HTTP exceptions become structured HTTP 500 responses instead of escaping the route.

✅ Success: every non-shutdown daemon route has a route-local containment boundary and returns JSON error bodies even when an internal operation explodes.
❌ If failed: revert the route being modified to the previous working state before touching the next route. Do not leave some routes hardened and others unguarded.

### Step 4: Harden daemon background tasks and startup watchers against unhandled exceptions
Open `silc/daemon/manager.py`.

Add explicit exception containment to these background/task paths:
1. `SilcDaemon._handle_session_task_done()`
2. `SilcDaemon._watch_restart()`
3. `SilcDaemon._watch_shutdown()`
4. `SilcDaemon._garbage_collect()`

Implement these exact rules:
1. Any exception in these functions must be logged with traceback details using the Step 1 helper.
2. No exception from these functions may escape and tear down the daemon process.
3. In `_watch_restart()`, if recreating or starting the new uvicorn server fails, clear the restart event, log the traceback, keep the daemon process alive, and continue the watcher loop.
4. In `_handle_session_task_done()`, if reading `task.exception()` itself raises, catch and log it.

✅ Success: session server failures and watcher failures are fully contained and logged, and the daemon process remains alive after those failures.
❌ If failed: revert the function currently being modified and stop. Do not leave any watcher function with half-applied try/except blocks.

### Step 5: Harden resurrect and restart flows so bad session state is quarantined instead of crashing the daemon
Open `silc/daemon/manager.py`.

Modify `SilcDaemon._resurrect_sessions()` and `SilcDaemon.start()` with these exact rules:
1. `_resurrect_sessions()` must never raise to its caller because of one bad saved session entry.
2. For each bad saved session entry, append a failure record to the returned `result["failed"]` list with the session name and reason.
3. For each bad saved session entry, log the full traceback using the Step 1 helper.
4. If a saved entry references a shell type that resolves to a path that cannot start, treat that entry as failed and continue to the next one.
5. `SilcDaemon.start()` must wrap the call to `_resurrect_sessions()` in a containment boundary that logs any unexpected top-level failure and continues to bring up the daemon API if possible.
6. `SilcDaemon.start()` must wrap `await self._daemon_server.serve()` in a try/except block that logs unexpected server exceptions before cleanup runs.

Do not silently discard failure information. Always log and continue where safe.

✅ Success: stale `sessions.json` entries can fail individually without preventing daemon startup, and daemon startup logs exact traceback details for unexpected resurrect/start errors.
❌ If failed: revert the resurrection/startup edits and stop. Do not leave startup in a state where `_resurrect_sessions()` can raise uncaught exceptions.

### Step 6: Update architecture docs for daemon request-failure boundaries
Open `docs/arch_api.md`.

Add or revise the daemon API architecture section so it states all of the following:
1. The daemon API installs app-wide exception handlers.
2. Unexpected route exceptions are returned as JSON HTTP 500 responses containing operation, detail, and traceback fields.
3. Route-local failures must not terminate the daemon process.
4. Session resurrection failures are quarantined per session entry and logged rather than crashing daemon startup.
5. Shutdown and killall remain the only expected process-exit operations.

Keep the text aligned with the implementation from Steps 2 through 5.

✅ Success: `docs/arch_api.md` clearly documents the new daemon request-failure boundary behavior and the shutdown exception to that rule.
❌ If failed: revert `docs/arch_api.md` to the pre-step content and stop.

### Step 7: Run focused verification that failed requests return errors without killing the daemon
Run the following targeted checks from `C:\Users\rx\001_Code\100_M\SILC` using `C:\Users\rx\001_Code\100_M\SILC\.venv\Scripts\python.exe`:
1. `python -m silc killall`
2. `python -m silc start base-session`
3. Send a daemon request that should fail validation, such as POST `/sessions` with `{"shell":"not-a-shell"}`. Confirm the response is HTTP 400 JSON and the daemon still answers `GET /sessions` afterward.
4. Send a daemon request that should trigger an internal session-start failure on Windows, using POST `/sessions` with `{"shell":"pwsh"}` if the environment still reproduces the PowerShell startup issue. Confirm the response is HTTP 500 JSON with error fields and that `GET /sessions` still responds afterward.
5. Read the current daemon log and confirm traceback details were written for the internal failure case.

Do not run the full test suite.

✅ Success: at least one validation failure and one internal failure produce JSON error responses without killing the daemon, and the daemon log contains traceback detail for the internal failure.
❌ If failed: capture the exact failing request, response, and daemon log output. Fix only the code necessary to restore the containment boundary, then rerun Step 7.

---

## Verification
- The daemon FastAPI app in `silc/daemon/manager.py` has explicit handlers for `HTTPException` and generic `Exception`.
- Non-shutdown daemon routes return JSON error bodies instead of causing browser-side network disconnects when internal failures occur.
- `create_session()` closes reserved sockets and leaves no partial session state on failure.
- `_watch_restart()`, `_watch_shutdown()`, `_garbage_collect()`, and `_handle_session_task_done()` no longer allow unhandled exceptions to escape.
- `_resurrect_sessions()` logs per-entry failures and continues processing later entries.
- `docs/arch_api.md` documents the containment boundary and the shutdown/killall exception.

## Rollback
- If the hardening cannot be stabilized, revert these files to HEAD:
  - `git checkout -- silc/daemon/manager.py`
  - `git checkout -- docs/arch_api.md`
- If any verification-only local state was created, stop the daemon with:
  - `C:\Users\rx\001_Code\100_M\SILC\.venv\Scripts\python.exe -m silc killall`
- After rollback, run `git status --short` and confirm only intentionally unrelated working-tree changes remain.
