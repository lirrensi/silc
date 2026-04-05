# Plan: Record-Driven Daemon Supervision
_Done means the daemon becomes the root reconciler: session records are desired state, PTY is the primary resource, the per-session server is a replaceable messenger, and runtime failures no longer take the daemon down._

---

# Checklist
- [x] Step 1: Add a session runtime model and supervision helpers
- [x] Step 2: Refactor SilcDaemon to own desired records and runtime separately
- [x] Step 3: Make session creation record-first and failure-contained
- [x] Step 4: Add reconciliation loops with generation safety and bounded backoff
- [x] Step 5: Rewire restart, resurrect, close, and kill around reconciliation
- [x] Step 6: Add focused tests for record survival and runtime replacement
- [x] Step 7: Run targeted verification and sync any implementation pointers

---

## Context
- The daemon lives in `silc/daemon/manager.py`.
- Session persistence and the desired-session registry live in `silc/utils/persistence.py` and `silc/daemon/registry.py`.
- Session runtime lives in `silc/core/session.py`.
- Per-session HTTP/WebSocket messenger apps are created by `silc/api/server.py`.
- Canonical daemon architecture already describes the new model in `docs/arch_daemon.md`, `docs/product.md`, and `docs/glossary.md`.
- The current code still treats live runtime maps and cleanup tasks too close to source-of-truth behavior. This plan moves authority to persisted records and daemon reconciliation.

## Prerequisites
- Repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- Use `C:\Users\rx\001_Code\100_M\SILC\.venv\Scripts\python.exe` for verification.
- Do not run the full test suite in this pass.
- Existing daemon processes should be stopped with `python -m silc killall` before targeted verification if needed.

## Scope Boundaries
- Do not change the web UI websocket client in `manager_web_ui/`.
- Do not change the Rust TUI client in `tui_client/`.
- Do not change the websocket binary framing protocol in `silc/api/server.py` unless a local refactor is required to attach a fresh messenger to a replaced PTY.
- Do not change CLI argument parsing in `silc/__main__.py`.
- Do not broaden session persistence format unless required for runtime-safe record loading.

---

## Steps

### Step 1: Add a session runtime model and supervision helpers
Create a new daemon-side module, preferably `silc/daemon/runtime.py`, that defines the runtime shape for a single desired session record.

Add these pieces:
1. A `SessionState` representation with explicit values for at least: `starting`, `running`, `degraded`, `backoff`, `stopping`, `stopped`.
2. A `SessionRuntime` dataclass that holds:
   - port
   - generation
   - state
   - `SilcSession | None`
   - `uvicorn.Server | None`
   - socket handle
   - server task handle
   - last error string
   - last traceback string
   - restart count
   - next retry time
3. Small pure helper functions for:
   - creating a fresh runtime object for a record
   - bumping generation
   - recording a failure into runtime state
   - deciding whether backoff has expired
   - formatting runtime state for logging and status responses

Keep the helpers small and explicit. Do not embed daemon request routing in this module.

✅ Success: `silc/daemon/runtime.py` exists and gives the daemon a single, explicit runtime model that is separate from the persistent record model.
❌ If failed: remove the new module and any imports that reference it, then stop. Do not continue with a partial runtime model.

### Step 2: Refactor SilcDaemon to own desired records and runtime separately
Open `silc/daemon/manager.py` and refactor `SilcDaemon` so that desired state and runtime state are separate concerns.

Make these exact structural changes:
1. Keep `self.registry` as the desired-record source of truth.
2. Replace direct runtime ownership with a runtime map such as `self.runtime_by_port: dict[int, SessionRuntime]`.
3. Remove any remaining assumption that `self.sessions` or `self.servers` are the authority for whether a record exists.
4. Add daemon-owned helper methods for:
   - looking up the desired record for a port or name
   - looking up or creating the runtime object for a record
   - ensuring a PTY exists for a runtime
   - ensuring a per-session server exists for a runtime
   - tearing down a runtime generation without deleting the record
   - deleting a record and then stopping reconciliation for that record
5. Route status/list/resolve code through record-plus-runtime lookup, not through runtime-only checks.

Keep the public CLI/API surface stable. The internal ownership model changes, but the external commands should still feel like the same SILC.

✅ Success: `SilcDaemon` can answer “what should exist?” from the registry and “what is currently alive?” from runtime separately.
❌ If failed: revert the `SilcDaemon` structural changes before moving on. Do not leave mixed authority in place.

### Step 3: Make session creation record-first and failure-contained
Open `silc/daemon/manager.py` and rewrite the nested `create_session()` route inside `SilcDaemon._create_daemon_api()`.

Make these exact behavior changes:
1. Validate the request first.
2. Persist the desired session record before launching PTY or server runtime.
3. Create or fetch the runtime object for the new record.
4. Realize the PTY and messenger server from that runtime.
5. If runtime realization fails, keep the record, mark the runtime degraded/backoff, and return a structured JSON error response instead of crashing the daemon.
6. If the request fails for validation reasons, return an HTTP 4xx response with a concise error.
7. If a partial socket, server, or PTY exists after a failure, close it and detach it from the runtime generation that failed.
8. Do not leave partial runtime references behind in the daemon maps after failure cleanup.

Use the same structured error payload shape already introduced in `silc/daemon/manager.py` during the request-failure boundary work.

✅ Success: a create request either produces a desired record plus runtime convergence or returns a structured error without taking the daemon down.
❌ If failed: revert the `create_session()` rewrite and stop. Do not continue while partial runtime cleanup is unreliable.

### Step 4: Add reconciliation loops with generation safety and bounded backoff
Open `silc/daemon/manager.py` and add daemon-owned reconciliation logic.

Implement the following rules:
1. The daemon MUST reconcile each desired record on startup and during normal operation.
2. If a runtime PTY dies, the daemon MUST replace the PTY while preserving the record.
3. If a per-session messenger server dies, the daemon MUST replace the server while preserving the record and PTY.
4. Each replacement MUST increment a generation number so stale callbacks cannot tear down the new runtime.
5. Bad configuration or repeated launch failure MUST move the runtime into `degraded` or `backoff` rather than hot-looping forever.
6. Reconciliation SHOULD retry after bounded backoff instead of using idle-timeout session death.
7. Garbage-collection code MUST stop treating idle time as a reason to delete desired sessions.

Move any idle-timeout-driven cleanup logic out of the session-death path. Session lifetime is controlled by record existence, not by idle time.

✅ Success: the daemon can keep trying to realize a desired record after runtime loss without deleting that record or wedging the process.
❌ If failed: revert the reconciliation changes and stop. Do not leave a half-supervisor that can still hot-loop or delete records spuriously.

### Step 5: Rewire restart, resurrect, close, and kill around reconciliation
Open `silc/daemon/manager.py` and update the lifecycle routes and startup path so they operate against desired records and runtime reconciliation.

Implement these exact semantics:
1. `restart_session()` must preserve the record and replace the PTY generation, then ensure the messenger server is attached to the fresh runtime.
2. `resurrect()` must re-read desired records and feed them into the same reconciliation path used by normal operation; resurrection is not a special ownership mode.
3. `close_session()` and `kill_session()` must remove the desired record first, then stop reconciliation, then tear down runtime.
4. `SilcDaemon.start()` must load persisted records, create runtime objects, and enter reconciliation without requiring every record to be healthy at boot.
5. `SilcDaemon._watch_restart()` and any startup watcher must restart the daemon HTTP server without losing record ownership or runtime supervision.
6. Any stale generation cleanup callback must ignore newer runtime generations.

✅ Success: restart/close/kill/resurrect all follow the same record-first ownership model, and startup resumes reconciliation rather than depending on a fragile one-shot resurrection path.
❌ If failed: revert the lifecycle rewiring and stop. Do not leave restart/close/kill split across old and new ownership rules.

### Step 6: Add focused tests for record survival and runtime replacement
Add or update targeted tests under `tests/` that prove the new daemon behavior.

Cover at least these cases:
1. A session create failure returns a structured error and leaves the daemon alive.
2. A desired record survives a PTY startup failure and is marked degraded/backoff instead of disappearing.
3. A desired record survives a messenger server failure and the daemon can recreate the server.
4. `restart` preserves the record while replacing runtime generation.
5. `close` and `kill` remove the record and stop reconciliation.
6. A stale generation callback cannot tear down a newer runtime.
7. Idle time does not delete a desired record.

Keep tests targeted. Do not invoke the full suite.

✅ Success: the tests clearly distinguish record death from runtime death and prove the daemon remains alive through runtime failure.
❌ If failed: revert the new/updated tests and stop. Do not let a flaky test layer obscure the daemon ownership model.

### Step 7: Run targeted verification and sync any implementation pointers
Run these targeted checks from `C:\Users\rx\001_Code\100_M\SILC`:
1. `python -m py_compile silc/daemon/manager.py silc/daemon/runtime.py`
2. A focused `pytest` selection for the new daemon tests only.
3. A short daemon smoke check that creates a session, forces one runtime failure case, and confirms the daemon still responds afterward.

If new module/file names or ownership notes changed materially, update the relevant implementation pointers in `docs/arch_daemon.md` only.

✅ Success: targeted checks pass and the daemon remains responsive after the failure cases used in the smoke check.
❌ If failed: capture the exact failing command and output, fix only the daemon ownership/reconciliation issue that caused it, and rerun the same targeted check.

---

## Verification
- `SilcDaemon` separates desired records from runtime state.
- The registry remains the source of truth for what should exist.
- PTY loss does not delete the desired record.
- Messenger/server loss does not delete the desired record or the PTY.
- Restart changes runtime generation, not record identity.
- Close/kill remove the record and stop reconciliation.
- Targeted tests prove the daemon stays alive through runtime failure.

## Rollback
- If the rewrite cannot be stabilized, revert these files to HEAD:
  - `git checkout -- silc/daemon/manager.py`
  - `git checkout -- silc/daemon/runtime.py`
  - `git checkout -- tests/<new-daemon-tests>.py`
  - `git checkout -- docs/arch_daemon.md` if implementation pointers changed
- Stop the daemon if needed with:
  - `C:\Users\rx\001_Code\100_M\SILC\.venv\Scripts\python.exe -m silc killall`
- After rollback, run `git status --short` and confirm only intentionally unrelated changes remain.
