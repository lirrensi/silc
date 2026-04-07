# Plan: Daemon-owned settings store
_Add a daemon-persisted shared settings store, expose read/merge APIs and CLI commands, and have both the manager UI and isolated session web UI consume it with built-in fallbacks._

---

# Checklist
- [ ] Step 1: Add daemon settings persistence helpers
- [ ] Step 2: Add daemon settings API and CLI commands
- [ ] Step 3: Hydrate manager UI from daemon settings
- [ ] Step 4: Teach isolated session web UI to read settings
- [ ] Step 5: Run verification tests and build checks

---

## Context

- The daemon already owns session persistence in `silc/utils/persistence.py` and manager lifecycle in `silc/daemon/manager.py`.
- The manager web UI currently stores theme/sidebar/home-grid state in browser `localStorage` through `manager_web_ui/src/stores/ui.ts`.
- The isolated session web page lives in `static/web/index.html` and currently hardcodes xterm theme and font settings.
- Canon now requires daemon-owned shared settings with `GET /settings` and `POST /settings`, plus `silc settings get` and `silc settings set <path> <value>`.

## Prerequisites

- Python dependencies are installed for the SILC project.
- Node dependencies are installed for `manager_web_ui/`.
- The working tree is clean enough to edit source files.
- The daemon settings file location must stay inside the SILC data directory.

## Scope Boundaries

- Do not change session PTY semantics, websocket framing, or command execution behavior.
- Do not change dormant-session resurrection rules beyond what settings persistence requires.
- Do not add manager-specific coupling into the isolated session web page.
- Do not remove the existing browser fallback behavior for theme/layout state until daemon settings are working.

---

## Steps

### Step 1: Add daemon settings persistence helpers

Create `silc/daemon/settings.py` with a small settings dataclass and deep-merge helpers for shared settings. Add daemon settings file read/write helpers in `silc/utils/persistence.py` for `settings.json`, including atomic writes when possible and a stable path inside the SILC data dir.

Also update any bootstrap code that loads daemon state so shared settings are loaded before clients read them.

✅ Success: `settings.json` can be loaded, merged, and written without touching `sessions.json`.
❌ If failed: stop editing client code, fix the persistence helpers first, and rerun the daemon settings tests before proceeding.

### Step 2: Add daemon settings API and CLI commands

Update `silc/daemon/manager.py` to expose `GET /settings` and `POST /settings`.

- `GET /settings` returns the current effective settings object.
- `POST /settings` deep-merges a JSON object into the stored settings and persists the result.
- Writes must be serialized with the same daemon metadata lock discipline used for session registry writes.

Update `silc/__main__.py` to add a top-level `settings` command group with:

- `silc settings get`
- `silc settings set <path> <value>`

The CLI must call the daemon API; it must not edit browser cache or session files directly.

✅ Success: the daemon returns settings over HTTP and the CLI can read and merge one path/value pair.
❌ If failed: stop and repair the daemon route or CLI wiring before touching the web UI.

### Step 3: Hydrate manager UI from daemon settings

Update `manager_web_ui/src/lib/daemonApi.ts` to include `getSettings()` and `updateSettings()`.

Update `manager_web_ui/src/stores/ui.ts`, `manager_web_ui/src/lib/themes.ts`, `manager_web_ui/src/main.ts`, and any related terminal theme wiring so the manager UI:

- fetches daemon settings on startup,
- uses daemon settings as the source of truth,
- keeps browser state as a fallback/cache only,
- applies manager theme and xterm theme/font defaults from settings.

Keep the existing local UI behavior working if the daemon settings call fails.

✅ Success: manager theme and terminal theme resolve from daemon settings, with local fallback when the daemon cannot be reached.
❌ If failed: do not touch the isolated web page yet; fix the manager settings hydration first.

### Step 4: Teach isolated session web UI to read settings

Update `static/web/index.html` so the per-session browser page attempts a best-effort `GET /settings` against the daemon, applies terminal appearance defaults when available, and falls back to built-in xterm defaults when settings are unreachable.

Keep the isolated page write-free for settings. The page may only read; it must not mutate shared settings.

✅ Success: the isolated page reads terminal defaults when possible and still works with built-in defaults if the daemon is unavailable.
❌ If failed: keep the page functional with built-in defaults and revisit only the read path.

### Step 5: Run verification tests and build checks

Run the focused Python tests for daemon persistence/settings and the relevant web UI tests/build steps for manager UI and the static web page.

Expected checks should cover:

- daemon settings load/merge/write behavior,
- `GET /settings` and `POST /settings`,
- CLI `settings get/set`,
- manager UI theme hydration,
- isolated session page fallback behavior.

✅ Success: all targeted tests and builds pass.
❌ If failed: fix the smallest failing layer first, then rerun the full verification set.

---

## Verification

- `pytest` or focused Python tests covering daemon settings persistence and daemon routes.
- `pnpm test` or targeted Vitest coverage for manager settings/theme hydration.
- Web UI build succeeds.
- `static/web/index.html` still loads and the terminal page still connects when settings fetch fails.

## Rollback

- Revert the settings API, CLI group, and client settings hydration changes together if the daemon settings store destabilizes session startup.
- Remove `settings.json` only after confirming no other code path depends on it.
- Restore the previous browser-local theme behavior if the manager UI cannot load daemon settings reliably.
