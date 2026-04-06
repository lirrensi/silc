# Plan: Dormant resurrect and graceful snapshot persistence
_Done means daemon startup restores desired sessions as dormant records, graceful stop paths save one raw snapshot per session keyed by `session_id`, `silc resurrect` materializes all persisted sessions, and the manager UI renders dormant sessions as sleeping/gray without allocating live terminal resources._

---

# Checklist
- [x] Step 1: Add snapshot persistence helpers keyed by session_id
- [x] Step 2: Extend daemon session snapshots with dormant metadata
- [x] Step 3: Load persisted desired records without creating runtime on daemon start
- [x] Step 4: Add daemon startup snapshot garbage collection
- [x] Step 5: Save raw snapshots during graceful shutdown and restart paths
- [x] Step 6: Delete orphan snapshot files when records are removed
- [x] Step 7: Make daemon resurrect explicitly materialize dormant records
- [x] Step 8: Fix CLI resurrect output to match daemon resurrect semantics
- [x] Step 9: Make manager session models support dormant sessions without eager terminal allocation
- [x] Step 10: Render dormant sessions as sleeping/gray and skip preview/websocket attachment
- [x] Step 11: Add backend tests for dormant restore and snapshot lifecycle
- [x] Step 12: Add frontend tests for dormant session rendering and lazy terminal allocation

---

## Context

- `silc/daemon/manager.py` currently loads `sessions.json` in `_load_persisted_desired_records()` and immediately calls `_get_or_create_runtime(entry, title=title)`. `SilcDaemon.start()` then calls `_reconcile_desired_sessions_once()`, which materializes every persisted session on daemon boot. This behavior must change.
- `silc/utils/persistence.py` already owns `SESSIONS_FILE`, session logs, and atomic write helpers. This module is the correct place for snapshot file helpers.
- `silc/core/session.py` exposes `SilcSession.get_snapshot_bytes()`, which returns the current raw PTY byte buffer. Reuse that method for graceful snapshot persistence.
- `silc/daemon/events.py` serializes manager-facing session metadata. The manager UI currently receives `alive` and `runtime_state` from this serializer.
- `manager_web_ui/src/stores/terminalManager.ts` currently allocates a real xterm instance inside `createSession()` for every daemon session. That eager allocation must stop for dormant sessions.
- `manager_web_ui/src/components/TerminalViewport.vue` currently calls `connectWebSocket()` as soon as a session exists. That must not happen for dormant sessions.
- `manager_web_ui/src/components/Sidebar.vue`, `manager_web_ui/src/views/SessionView.vue`, and any card/sidebar row components must visually distinguish dormant sessions from live sessions.
- Existing docs already say snapshots are keyed by `session_id` and dormant snapshots stay on disk until explicitly needed. The code must now match the docs.

## Prerequisites

- Work from repository root: `C:\Users\rx\001_Code\100_M\SILC`.
- Python commands must use `uv`. Node commands must use `pnpm`.
- Before touching frontend code, confirm `manager_web_ui/package.json` dependencies are already installed. If dependencies are missing, stop and report instead of installing new packages unless strictly required.
- Use the existing test suites in `tests/` and `manager_web_ui/src/__tests__/`. Do not invent a new test runner.

## Scope Boundaries

- Do not add dormant-session preview serving from the daemon in this plan. Dormant sessions intentionally show no preview.
- Do not add per-session click-to-materialize behavior in the manager UI in this plan. Materialization is only through `silc resurrect` for now.
- Do not change shell launch semantics in `silc/core/pty_manager.py` or shell helper scripts.
- Do not add periodic background snapshot checkpointing. This plan only covers graceful stop paths.
- Do not add snapshot history/versioning. Keep exactly one latest snapshot file per `session_id`.

---

## Steps

### Step 1: Add snapshot persistence helpers keyed by session_id

Open `silc/utils/persistence.py` and add a snapshot storage section next to the existing session persistence helpers.

Add all of the following helpers:

- `SNAPSHOTS_DIR = DATA_DIR / "snapshots"`
- `def get_session_snapshot_path(session_id: str) -> Path`
- `def write_session_snapshot(session_id: str, data: bytes) -> None`
- `def read_session_snapshot(session_id: str) -> bytes`
- `def remove_session_snapshot(session_id: str) -> None`
- `def list_session_snapshot_ids() -> set[str]`
- `def garbage_collect_session_snapshots(valid_session_ids: set[str]) -> list[str]`

Requirements for these helpers:

- Use `session_id` in file names, not port or name.
- Use one file per session: `session_<session_id>.bin`.
- `write_session_snapshot()` must create `SNAPSHOTS_DIR` if missing and overwrite atomically when possible.
- `read_session_snapshot()` must return `b""` when the file is missing or unreadable.
- `garbage_collect_session_snapshots()` must delete only files matching the snapshot naming pattern and return the removed `session_id` values.
- Update `__all__` to export the new helpers.

✅ Success: `silc/utils/persistence.py` exposes the new snapshot helpers, and snapshot file naming is based on `session_id`.
❌ If failed: Revert only the snapshot-helper edits in `silc/utils/persistence.py`, restore imports/exports to their previous state, and stop.

### Step 2: Extend daemon session snapshots with dormant metadata

Open `silc/daemon/events.py` and change `serialize_session_snapshot()` so manager clients can reliably identify dormant sessions without requiring a live runtime.

Make these exact changes:

- Add a `dormant` boolean field to the returned snapshot dictionary.
- When `runtime is None`, return `alive=False`, `runtime_state="dormant"`, and `dormant=True`.
- When a runtime exists but no live `SilcSession` is attached, preserve the runtime state string and set `dormant` to `False` unless the runtime state explicitly represents dormancy.
- Keep all existing fields (`port`, `name`, `title`, `session_id`, `shell`, `cwd`, `title_updated_at`, `idle_seconds`, `alive`, `runtime_state`) in place.

Do not remove or rename existing payload fields because the web UI tests already consume them.

✅ Success: manager snapshot payloads can distinguish dormant records from dead/running runtime using `dormant` and `runtime_state`.
❌ If failed: Restore `serialize_session_snapshot()` to the previous field set and stop.

### Step 3: Load persisted desired records without creating runtime on daemon start

Open `silc/daemon/manager.py` and change persisted-record loading so daemon boot stays lazy.

Make these exact edits:

- In `_load_persisted_desired_records()`, remove the call to `_get_or_create_runtime(entry, title=title)`.
- Keep `registry.add(...)` behavior exactly as-is so desired records still load from `sessions.json`.
- Preserve `result["loaded"]` and `result["failed"]` return shapes.
- In `SilcDaemon.start()`, remove the eager call to `_reconcile_desired_sessions_once()` that currently runs immediately after `_load_persisted_desired_records()`.

Do not remove the reconcile loop itself; the daemon still needs it after explicit materialization.

✅ Success: daemon startup loads desired records into `SessionRegistry` but does not create `SessionRuntime`, PTYs, servers, or sockets for those records.
❌ If failed: Restore the eager runtime creation and start-path reconcile calls, then stop.

### Step 4: Add daemon startup snapshot garbage collection

Open `silc/daemon/manager.py` and `silc/utils/persistence.py` imports, then insert startup GC immediately after persisted desired records are loaded.

Implement the following:

- Import `garbage_collect_session_snapshots` into `silc/daemon/manager.py`.
- In `SilcDaemon.start()`, after `_load_persisted_desired_records()` succeeds and before the daemon server is created, compute `valid_session_ids` from `self.registry.list_all()`.
- Call `garbage_collect_session_snapshots(valid_session_ids)`.
- Write one daemon log line when snapshot files are removed. Include the removed `session_id` values or count.

Do not load any snapshot bytes into memory during this step.

✅ Success: daemon startup deletes orphan snapshot files before serving requests and logs the cleanup work.
❌ If failed: Remove the startup GC call, remove the new import, and stop.

### Step 5: Save raw snapshots during graceful shutdown and restart paths

Open `silc/daemon/manager.py` and add one daemon-owned helper that writes snapshots for live sessions during graceful stop.

Implement the following:

- Add a helper named `_persist_runtime_snapshot(port: int) -> None` or a similarly explicit name inside `SilcDaemon`.
- The helper must:
  - look up the desired record by port
  - look up the live runtime/session by port
  - return immediately if no desired record exists
  - return immediately if no live `SilcSession` exists
  - call `session.get_snapshot_bytes()`
  - call `write_session_snapshot(entry.session_id, snapshot_bytes)`
  - write a daemon log entry on success
- In `_watch_shutdown()`, call this helper once for each port before `_ensure_cleanup_task(port, remove_record=False)` runs.
- In any other graceful stop path inside `SilcDaemon` that can bypass `_watch_shutdown()`, add the same snapshot save call before runtime teardown.

Do not save snapshots during `killall`, `close`, or force-kill cleanup paths.

✅ Success: graceful daemon shutdown writes one snapshot file per live session before sessions are torn down.
❌ If failed: Remove the snapshot-save helper and all new call sites, then stop.

### Step 6: Delete orphan snapshot files when records are removed

Open `silc/daemon/manager.py` and delete snapshot files when a session record is intentionally destroyed.

Add snapshot removal to these exact paths:

- `_cleanup_session(..., remove_record=True)` after `self.registry.remove(port)` succeeds.
- Any `killall` record-destruction path that removes all desired records and clears `sessions.json`.
- Any rollback path that removes a newly-created desired record after start failure, if a snapshot file could exist for that record.

Use `remove_session_snapshot(entry.session_id)` for record-backed removals.

Do not remove snapshot files when `remove_record=False` because graceful shutdown preserves dormant records.

✅ Success: closing or killing a session removes the session record and the matching snapshot file, while graceful shutdown preserves both.
❌ If failed: Remove only the new snapshot-deletion calls and stop.

### Step 7: Make daemon resurrect explicitly materialize dormant records

Open `silc/daemon/manager.py` and change `_resurrect_sessions()` so `POST /resurrect` becomes the one eager materialization path.

Make these exact changes:

- Keep `_load_persisted_desired_records()` as the first action so persisted records missing from the current registry are loaded.
- Build the resurrect result around actual materialization work, not just loaded records.
- Iterate `self.registry.list_all()` and call `_reconcile_record(entry)` or `_reconcile_desired_sessions_once()` after the records are present so dormant sessions become live PTYs + servers.
- Return a payload that clearly reports materialized sessions in a `restored` list because `silc/__main__.py` already expects that key.
- Preserve `failed` reporting for entries that could not be materialized.

The restored payload must describe all sessions materialized by the request, not only sessions newly read from disk.

✅ Success: `POST /resurrect` returns `restored` entries and every desired record is materialized by the end of the request.
❌ If failed: Restore the previous `_resurrect_sessions()` behavior and stop.

### Step 8: Fix CLI resurrect output to match daemon resurrect semantics

Open `silc/__main__.py` and align the `resurrect()` command with the daemon payload created in Step 7.

Make these exact edits:

- Keep `requests.post(_daemon_url("/resurrect"), timeout=30)`.
- Read `restored` and `failed` from the response JSON.
- Print a success message that says materialized or restored sessions were brought live.
- If `restored` is empty and `failed` is empty, print `No sessions to resurrect`.

Do not add new CLI flags in this plan.

✅ Success: `silc resurrect` prints sensible output based on the daemon response and no longer depends on nonexistent payload keys.
❌ If failed: Restore the prior CLI message body and stop.

### Step 9: Make manager session models support dormant sessions without eager terminal allocation

Open these files:

- `manager_web_ui/src/types/session.ts`
- `manager_web_ui/src/lib/daemonApi.ts`
- `manager_web_ui/src/stores/terminalManager.ts`

Implement these exact structural changes:

- Add `'dormant'` to `SessionStatus` in `manager_web_ui/src/types/session.ts`.
- Add `dormant: boolean` to the `DaemonSession` interface in both `session.ts` and `daemonApi.ts`.
- Change the `Session` interface so terminal-bearing fields can be absent before attachment:
  - `terminal: Terminal | null`
  - `fitAddon: FitAddon | null`
  - keep existing nullable websocket-related fields
- In `manager_web_ui/src/stores/terminalManager.ts`, stop calling `initializeSessionTerminal(session)` inside `createSession()`.
- Add a helper that lazily creates the xterm instance only when `attach()` needs a terminal for a live session.
- In `upsertDaemonSession()` or `updateSessionMetadata()`, set `session.status = 'dormant'` when `daemonSession.dormant === true`.
- Preserve existing live-session behavior for non-dormant sessions.

Any function in `terminalManager.ts` that currently assumes `session.terminal` or `session.fitAddon` always exists must be guarded before access. Add explicit early returns where necessary.

✅ Success: dormant sessions can exist in Pinia state without xterm instances, and live sessions still create terminals on first attach.
❌ If failed: Restore eager terminal initialization and remove the new dormant session fields, then stop.

### Step 10: Render dormant sessions as sleeping/gray and skip preview/websocket attachment

Open these frontend files and wire dormant behavior through the visible UI:

- `manager_web_ui/src/components/TerminalViewport.vue`
- `manager_web_ui/src/views/SessionView.vue`
- `manager_web_ui/src/components/Sidebar.vue`
- Any session-row or session-card component used by the sidebar/home grid, such as `manager_web_ui/src/components/SidebarSessionRow.vue` and `manager_web_ui/src/components/SessionCard.vue`

Make these exact behavior changes:

- In `TerminalViewport.vue`, before calling `attachAndConnect()`, check the daemon-backed session status. If the session is dormant, do not call `connectWebSocket()`, do not create a preview terminal, and render a sleeping/gray placeholder instead.
- In `SessionView.vue`, if the current session is dormant, show a non-interactive sleeping state instead of trying to reconnect to a nonexistent session port.
- In sidebar and card components, add a gray/desaturated dormant visual state and a dormant indicator distinct from active/idle/dead.
- Keep navigation intact: dormant sessions still appear in lists and can still open the session route.

Do not add automatic materialization-on-click in this plan.

✅ Success: the manager UI shows dormant sessions as sleeping/gray, no preview is rendered, and no websocket/session-port calls are attempted for dormant sessions.
❌ If failed: Restore prior UI rendering and websocket attachment logic, then stop.

### Step 11: Add backend tests for dormant restore and snapshot lifecycle

Open backend tests in `tests/test_daemon.py`, `tests/test_resurrect.py`, and any other directly relevant daemon test file.

Add tests for all of the following behaviors:

- graceful shutdown writes snapshot files keyed by `session_id`
- daemon startup `_load_persisted_desired_records()` plus `start()` leaves restored sessions dormant instead of live
- startup snapshot GC removes files whose `session_id` is absent from `sessions.json`
- `POST /resurrect` materializes dormant sessions and returns a `restored` payload
- close/kill/killall remove matching snapshot files when records are removed

Use `tmp_path` and monkeypatched persistence paths exactly like existing persistence tests. If snapshot helper tests fit better in `tests/test_resurrect.py`, keep them there.

✅ Success: backend tests cover dormant restore, graceful snapshot save, startup snapshot GC, and snapshot deletion on record removal.
❌ If failed: Remove only the newly-added backend tests and stop.

### Step 12: Add frontend tests for dormant session rendering and lazy terminal allocation

Open frontend tests in `manager_web_ui/src/__tests__/` and add or extend tests covering dormant sessions.

Add tests for all of the following:

- `terminalManager` does not allocate an xterm instance when reconciling a dormant daemon session
- `TerminalViewport` does not call websocket connection helpers for dormant sessions
- sidebar/session-card components render dormant sessions with sleeping/gray state
- `SessionView` shows a dormant placeholder instead of trying to reconnect to a live session port

Reuse existing mocked `listSessions()` and websocket mocks where possible.

✅ Success: frontend tests prove dormant sessions remain non-interactive and lazy until materialized.
❌ If failed: Remove only the newly-added frontend tests and stop.

---

## Verification

Run these commands from `C:\Users\rx\001_Code\100_M\SILC` after all code changes are complete:

1. `uv run pytest tests/test_resurrect.py tests/test_daemon.py`
2. `pnpm --dir manager_web_ui test:unit`

End-to-end behavior to confirm manually if the automated tests pass:

1. Start at least one session with `uv run python -m silc start <name>`.
2. Produce visible terminal output in that session.
3. Run `uv run python -m silc shutdown`.
4. Confirm `sessions.json` still contains the record and `snapshots/session_<session_id>.bin` exists.
5. Start the daemon again without calling `silc resurrect`.
6. Confirm `uv run python -m silc list` shows the session record but the session port is not listening.
7. Open the manager UI and confirm the session row/card is gray/sleeping with no preview.
8. Run `uv run python -m silc resurrect`.
9. Confirm the session becomes live again and the per-session port responds.

The plan is complete only when both automated command sets pass and the manual dormant→resurrect flow behaves exactly as listed above.

## Rollback

If a critical daemon change leaves startup or shutdown broken and the issue cannot be recovered quickly:

1. Revert all uncommitted changes to the files touched by this plan.
2. Delete any new snapshot helper files or snapshot test fixtures created by this plan.
3. Remove snapshot files from the test data directory if tests created them.
4. Re-run `uv run pytest tests/test_resurrect.py tests/test_daemon.py` to confirm the repository is back to the pre-plan baseline.

Plan complete. Handing off to Executor.
