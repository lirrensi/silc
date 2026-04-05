# Plan: Daemon Manager Event Broadcasts
_Done means the daemon publishes namespaced `session/<event>` updates through a daemon-level websocket using the existing binary frame envelope, and the manager web UI stays in sync without manual refresh when sessions are created, removed, restarted, or change metadata._

---

# Checklist
- [x] Step 1: Add daemon event bus and websocket frame helpers
- [x] Step 2: Emit namespaced session events from daemon lifecycle and metadata hooks
- [x] Step 3: Expose daemon websocket broadcasts for manager clients
- [x] Step 4: Add manager web UI daemon-events client and state reconciliation
- [x] Step 5: Add focused backend and frontend tests for daemon events
- [ ] Step 6: Run focused verification for Python and web UI

---

## Context
- The daemon management API lives in `silc/daemon/manager.py`.
- Desired session metadata lives in `silc/daemon/registry.py`.
- Per-session websocket framing helpers currently live only inside `silc/api/server.py`.
- The manager web UI fetch client lives in `manager_web_ui/src/lib/daemonApi.ts`.
- The manager session store lives in `manager_web_ui/src/stores/terminalManager.ts`.
- The manager session list currently refreshes by HTTP fetch in `manager_web_ui/src/components/Sidebar.vue`, `manager_web_ui/src/views/HomeView.vue`, `manager_web_ui/src/components/TerminalViewport.vue`, and reconnect flows in `manager_web_ui/src/views/SessionView.vue`.
- The existing session websocket binary envelope is `[4-byte big-endian header length][JSON header UTF-8 bytes][raw payload bytes]`.
- The user-approved daemon event namespace format is `session/<event>` such as `session/created` and `session/cwd_changed`.
- The user-approved internal event emitter library is `pyee`.

## Prerequisites
- Repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- Python project dependencies are installed well enough to run repository pytest targets.
- Node dependencies for `manager_web_ui/` are already installed.
- The change must keep per-session websocket behavior in `silc/api/server.py` working exactly as it works now.
- The change must reuse the existing binary websocket envelope instead of inventing a second manager-specific wire format.

## Scope Boundaries
- Do not change shell bootstrap behavior in `static/scripts/` during this plan.
- Do not change PTY read or OSC parsing logic in `silc/core/session.py` during this plan.
- Do not change CLI command syntax or add new CLI commands.
- Do not replace per-session websocket URLs in `silc/api/server.py`; manager events must be a separate daemon websocket path.
- Do not edit built frontend artifacts under `static/`.
- Do not update canon docs during this plan.

---

## Steps

### Step 1: Add daemon event bus and websocket frame helpers
Open `pyproject.toml` and add `pyee` to the main project dependency list.

Create one new Python module under `silc/daemon/` dedicated to daemon event transport, for example `silc/daemon/events.py`. Put all daemon-event-specific helpers in that module instead of growing `silc/daemon/manager.py` further.

In `silc/daemon/events.py`, add these focused pieces:
1. A small immutable event payload builder that returns a full manager event header dictionary with keys `type`, `session`, and any event-specific fields needed by the UI.
2. Binary websocket frame helpers that match the exact envelope already used in `silc/api/server.py`.
3. A lightweight broadcaster object that owns:
   - one `AsyncIOEventEmitter` from `pyee.asyncio`
   - the set of connected daemon websocket clients
   - a method to publish one event header to all active clients
   - a method to register one websocket client
   - a method to unregister one websocket client
4. Small helper functions that serialize a `SessionEntry` and runtime-derived liveness into the stable snapshot shape already returned by `GET /sessions`.

Do not duplicate framing logic inline in route functions. Put the reusable encode helper in `silc/daemon/events.py` and import it where needed.

✅ Success: `pyproject.toml` declares `pyee`, and a new focused module under `silc/daemon/` owns daemon-event framing, broadcasting, and session-snapshot serialization helpers.
❌ If failed: remove the partial new module and the `pyee` dependency line, restore `pyproject.toml`, and stop. Do not continue with event-bus logic scattered across `silc/daemon/manager.py`.

### Step 2: Emit namespaced session events from daemon lifecycle and metadata hooks
Open `silc/daemon/manager.py` and wire the new broadcaster into `SilcDaemon`.

Make these exact event sources publish namespaced `type` values:
1. After a session record is successfully created and persisted in `create_session`, publish `session/created` with the full session snapshot.
2. When a session record is removed by close, kill, shutdown cleanup, or rollback cleanup, publish `session/removed` with the last known session snapshot before deletion.
3. When a runtime finishes starting and the session becomes available, publish `session/started` with the current session snapshot.
4. When a runtime is intentionally restarted, publish `session/restarted` after the fresh runtime is established.
5. When a live title change reaches `_handle_session_title_change`, publish `session/title_changed` with the full updated session snapshot.
6. When a live cwd change reaches `_handle_session_cwd_change`, publish `session/cwd_changed` with the full updated session snapshot.
7. For publishes in items 1 and 3 through 6, also publish `session/updated` with the same full session snapshot immediately after the specific event so the manager UI can reconcile from one generic path.
8. Do not publish a trailing `session/updated` after `session/removed`; a post-removal upsert would re-create the deleted session in the manager UI.

The session snapshot in every event must include at least `port`, `name`, `title`, `session_id`, `shell`, `cwd`, `title_updated_at`, `alive`, and `runtime_state`.

If the daemon already has the data in memory, do not make HTTP calls to itself. Build the snapshot from `SessionRegistry`, `SessionRuntime`, and `SilcSession` state only.

✅ Success: `silc/daemon/manager.py` publishes namespaced `session/<event>` updates from session creation, removal, start, restart, title change, and cwd change paths without introducing self-HTTP calls.
❌ If failed: remove the incomplete publish calls from `silc/daemon/manager.py`, keep only the Step 1 module if it is still self-contained and correct, and stop. Do not continue with partially-emitted lifecycle coverage.

### Step 3: Expose daemon websocket broadcasts for manager clients
Open `silc/daemon/manager.py` and add one daemon-level websocket route on the management API. Use a path that does not collide with per-session websocket endpoints. Use `/events` unless the file already reserves that path for another purpose.

Implement the route with this exact behavior:
1. Accept the websocket connection.
2. Register the websocket with the broadcaster from Step 1.
3. Immediately send one `session/snapshot` frame whose header contains a `sessions` array with the full current daemon session list in the same shape as `GET /sessions`.
4. Keep the connection open until disconnect.
5. The route must not require the client to send any application messages.
6. On disconnect or send failure, unregister the websocket cleanly.
7. All outbound daemon-event websocket messages must use the same binary envelope as the session websocket protocol.

Do not change the existing per-session `/ws` route in `silc/api/server.py`. The daemon events websocket must stay fully separate.

✅ Success: the daemon management API serves a websocket route that sends a bootstrap `session/snapshot` frame and then broadcasts framed `session/<event>` messages to connected clients.
❌ If failed: remove the websocket route and broadcaster registration code from `silc/daemon/manager.py`, keep the underlying Step 1 helpers only if they remain unused and harmless, and stop. Do not continue with a half-live daemon websocket.

### Step 4: Add manager web UI daemon-events client and state reconciliation
Create one new frontend module such as `manager_web_ui/src/lib/daemonEvents.ts` to own the daemon websocket connection. Do not overload `manager_web_ui/src/lib/websocket.ts`, because that file is for per-session terminals.

In `manager_web_ui/src/lib/daemonEvents.ts`, implement these exact behaviors:
1. Build the daemon websocket URL from `getDaemonUrl()` in `manager_web_ui/src/lib/daemonApi.ts` by switching `http` to `ws` and appending `/events`.
2. Set `binaryType = 'arraybuffer'`.
3. Reuse or mirror the existing frontend frame decode helper so daemon events parse the same binary envelope.
4. On `session/snapshot`, call `manager.reconcileSessions(...)` with the `sessions` array from the header.
5. On `session/created`, `session/started`, `session/restarted`, `session/title_changed`, `session/cwd_changed`, and `session/updated`, upsert the single session from the event payload into the store.
6. On `session/removed`, remove the session from the store by port.
7. Add minimal reconnect behavior so the daemon events websocket attempts to reconnect after unexpected close.

Open `manager_web_ui/src/stores/terminalManager.ts` and add one focused action that upserts one `DaemonSession` object without requiring a full list fetch. Reuse the existing create-or-update logic instead of duplicating field assignments.

Open `manager_web_ui/src/App.vue` and start the daemon events websocket once for the whole manager application lifecycle. Also stop or close the websocket on app teardown if the component already has lifecycle cleanup.

Remove manager-wide dependence on manual HTTP refresh for live correctness. Keep `listSessions()` only for fallback flows that still need an explicit fetch, but do not require mount-time fetches in both `Sidebar.vue` and `HomeView.vue` just to discover ordinary live daemon changes.

✅ Success: the manager web UI keeps the session list synchronized from the daemon websocket, can upsert one session event without a full refresh, and uses a dedicated daemon-events client separate from per-session terminal websockets.
❌ If failed: revert `manager_web_ui/src/lib/daemonEvents.ts`, `manager_web_ui/src/stores/terminalManager.ts`, and `manager_web_ui/src/App.vue` plus any fetch-removal changes, then stop. Do not continue with mixed ownership between polling and partial event sync.

### Step 5: Add focused backend and frontend tests for daemon events
Add or update focused tests in `tests/` and `manager_web_ui/src/__tests__/`.

Backend coverage must verify all of these:
1. The daemon websocket endpoint sends an initial `session/snapshot` frame after connect.
2. Creating a session causes `session/created` and `session/updated` to be published.
3. A title callback publish path emits `session/title_changed` and `session/updated`.
4. A cwd callback publish path emits `session/cwd_changed` and `session/updated`.
5. Removing a session emits `session/removed`.

Frontend coverage must verify all of these:
1. The daemon-events client decodes a `session/snapshot` frame and reconciles the store.
2. The daemon-events client decodes a single-session update event and upserts the session.
3. The daemon-events client decodes `session/removed` and removes the store entry.
4. The daemon-events client reconnect logic does not open duplicate active sockets when one is already connected.

Use the existing binary websocket frame format in test fixtures instead of inventing test-only JSON shortcuts.

✅ Success: repository tests cover the daemon bootstrap snapshot, namespaced event emission, frontend reconciliation, and store removal paths.
❌ If failed: revert only the new daemon-event tests that are incorrect, keep the implementation in place, repair the test fixtures to match the shipped protocol, and rerun Step 5 before moving on.

### Step 6: Run focused verification for Python and web UI
Run these commands from the repository root unless a different working directory is stated:
1. `pytest tests/test_daemon.py tests/test_daemon_runtime_reconciler.py tests/test_session_live_cwd.py tests/test_osc_parser.py`
2. In `manager_web_ui/`: `npm run test:unit -- daemonEvents websocket`
3. In `manager_web_ui/`: `npm run build`

If a command fails because the daemon-event change broke existing behavior, fix only the code required to make the planned daemon-event implementation pass. Do not widen scope to unrelated refactors.

Local blocker note for this task pass: the focused pytest command is currently blocked by the local Python environment before repository tests start. First attempt with the exact Step 6 command fails during pytest plugin autoload with `ModuleNotFoundError: No module named 'anyio._core'` from the globally installed `anyio` package. One bounded retry with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` then fails because `pytest_asyncio` is not installed in that local interpreter. Leave this step unchecked unless the local environment is repaired.

✅ Success: the focused Python tests pass, the focused frontend unit tests pass, and the frontend build passes.
❌ If failed: capture the exact failing command and output, fix the exact daemon-event regression, rerun the same command, and stop only if the failure is unrelated or cannot be resolved without leaving the plan scope.

---

## Verification
- `pyproject.toml` includes `pyee`.
- A dedicated daemon event helper module exists under `silc/daemon/`.
- `silc/daemon/manager.py` exposes a daemon websocket endpoint separate from session `/ws`.
- Daemon websocket frames use the existing binary envelope and namespaced `session/<event>` types.
- The daemon websocket sends `session/snapshot` immediately after connect.
- The manager web UI owns a dedicated daemon-events client module separate from per-session `manager_web_ui/src/lib/websocket.ts`.
- `manager_web_ui/src/stores/terminalManager.ts` can upsert one daemon session from one event.
- The manager session list updates without requiring a manual refresh after create, remove, title change, or cwd change.
- The focused pytest target passes.
- The focused frontend tests and build pass.

## Rollback
- If the implementation cannot be stabilized, revert the modified files to repository HEAD with:
  - `git checkout -- pyproject.toml`
  - `git checkout -- silc/daemon/manager.py`
  - `git checkout -- silc/daemon/registry.py`
  - `git checkout -- tests/test_daemon.py tests/test_daemon_runtime_reconciler.py tests/test_osc_parser.py tests/test_session_live_cwd.py`
  - `git checkout -- manager_web_ui/src/App.vue`
  - `git checkout -- manager_web_ui/src/lib/daemonApi.ts`
  - `git checkout -- manager_web_ui/src/stores/terminalManager.ts`
  - `git checkout -- manager_web_ui/src/__tests__/websocket.spec.ts`
- Remove any newly added files created by this plan if rollback is required, including:
  - `del silc\daemon\events.py`
  - `del manager_web_ui\src\lib\daemonEvents.ts`
  - `del manager_web_ui\src\__tests__\daemonEvents.spec.ts`
- After rollback, run `git status` and confirm that only `agent_chat/plan_daemon_manager_events_2026-04-05.md` remains changed.
