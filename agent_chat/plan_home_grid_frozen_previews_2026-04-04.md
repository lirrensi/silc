# Plan: Home Grid Frozen Terminal Previews
_Replace the Home page terminal wall with a Home-only layout selector and frozen, color-preserving xterm previews that refresh on interval, mount only while Home is visible, and never participate in the interactive session page._

---

# Checklist
- [x] Step 1: Add Home-only grid state and selector UI
- [x] Step 2: Add frozen xterm preview rendering path
- [x] Step 3: Replace Home grid cards with snapshot previews
- [x] Step 4: Add visibility-based mount/unmount and refresh throttling
- [x] Step 5: Add tests for Home-only selector and preview lifecycle
- [x] Step 6: Build and verify the web UI

---

## Context

The current Home page uses live `TerminalViewport` instances inside `SessionCard`, which makes the dashboard look like a small terminal wall and keeps live session machinery in the overview. The requested shape is different:

- Home is a **dashboard**, not an interactive terminal page.
- Home gets a **layout selector inside Home only** (`2x2`, `3x3`, `4x4`).
- The preview cards should look like terminals, with colors, but should be **frozen snapshots**.
- No input, no websocket ownership, no resize dance for Home previews.
- The session detail page keeps the full live terminal behavior.

Relevant files:

- `manager_web_ui/src/views/HomeView.vue`
- `manager_web_ui/src/components/SessionCard.vue`
- `manager_web_ui/src/components/TerminalViewport.vue`
- `manager_web_ui/src/stores/terminalManager.ts`
- `manager_web_ui/src/lib/websocket.ts`
- `manager_web_ui/src/lib/daemonApi.ts`
- `manager_web_ui/src/types/session.ts`
- `manager_web_ui/src/stores/ui.ts`
- `manager_web_ui/src/__tests__/App.spec.ts`
- `manager_web_ui/src/__tests__/Sidebar.spec.ts`

The backend already exposes rendered session output and snapshot data sources, so this pass should prefer the existing API/byte source instead of inventing new backend contracts.

---

## Scope Boundaries

**IN SCOPE:**

- Home-only grid selector and layout persistence in the frontend.
- Frozen xterm preview cards that render from snapshot bytes and refresh periodically.
- Visibility-based mounting so previews only exist while visible and while the user is on Home.
- Replacing the current Home live-terminal grid.
- Tests for the new Home behavior.

**OUT OF SCOPE:**

- Do not move the selector into the global app shell or session pages.
- Do not change the interactive session page terminal behavior.
- Do not introduce drag/drop re-layout in this pass.
- Do not add live websocket streaming to the Home previews.
- Do not redesign the overall visual theme.

---

## Steps

### Step 1: Add Home-only grid state and selector UI

Open `manager_web_ui/src/stores/ui.ts` and `manager_web_ui/src/views/HomeView.vue`.

Add a Home-only layout state that tracks one of three grid densities:

- `2x2`
- `3x3`
- `4x4`

Requirements:

- The selector lives **inside HomeView only**.
- It should appear at the top of the Home pane.
- It must not appear in the session view or the sidebar/global app chrome.
- Persist the selected grid density in the existing UI store if practical.
- If persistence is not already available, keep it local to the Home page for this pass.

✅ Success: Home has a visible grid selector, and other routes remain unchanged.
❌ If failed: do not widen the UI scope; keep the selector Home-only.

---

### Step 2: Add frozen xterm preview rendering path

Create a new component or helper path for read-only preview terminals, separate from the live `TerminalViewport` used on session pages.

Behavior:

- Create an xterm instance for a preview card.
- Feed it snapshot bytes or ANSI-colored rendered output.
- Do **not** attach input handlers.
- Do **not** connect a live websocket.
- Do **not** resize as if it were an interactive session.
- Freeze the preview until the next refresh tick.

Implementation guidance:

- Keep the live session page untouched.
- Prefer a dedicated preview component over overloading `TerminalViewport` with too many modes.
- If the backend data path is already available as bytes, consume that directly.

✅ Success: a preview card can render a static colored terminal snapshot without becoming interactive.
❌ If failed: do not fall back to plain-text cards unless absolutely necessary; preserve xterm rendering.

---

### Step 3: Replace Home grid cards with snapshot previews

Open `manager_web_ui/src/views/HomeView.vue` and `manager_web_ui/src/components/SessionCard.vue`.

Replace the current Home grid behavior so it renders the new frozen preview cards instead of the live `TerminalViewport`.

Requirements:

- Each visible card should render to its grid slot size.
- A single session should still occupy a slot cleanly when the grid is sparse.
- The grid should scale by selector choice, not by changing the live session page.
- If there are more sessions than slots, show only the visible subset in this pass and leave overflow handling as a follow-up unless it is trivial.

✅ Success: Home cards display as frozen terminal previews rather than live terminals.
❌ If failed: do not keep the old live terminal wall as the default Home experience.

---

### Step 4: Add visibility-based mount/unmount and refresh throttling

Add lifecycle control so Home previews are cheap.

Requirements:

- Preview instances exist only while Home is mounted.
- Only visible cards mount preview xterms.
- When navigating away from Home, dispose all preview instances.
- Refresh cadence should be interval-based, not real-time.
- Throttle snapshot refreshes so not every card fetches at once.

Recommended shape:

- Use an `IntersectionObserver` or viewport visibility signal.
- Keep a small refresh queue.
- Consider a cached snapshot per session so cards remount quickly.

✅ Success: hidden/offscreen previews do not keep live DOM or terminal instances around.
❌ If failed: do not keep preview xterms alive outside Home or while invisible.

---

### Step 5: Add tests for Home-only selector and preview lifecycle

Add or update tests in the web UI test suite.

Verify:

- Home shows the selector; session pages do not.
- Preview cards render from the snapshot path.
- Preview instances mount/unmount with visibility and route changes.
- The Home grid no longer depends on live websocket behavior.

✅ Success: tests cover the Home-only selector and the frozen preview lifecycle.
❌ If failed: keep tests focused on Home behavior only; do not rewrite session-page tests unless needed.

---

### Step 6: Build and verify the web UI

Run the frontend verification path used by this repo.

Minimum verification:

- web UI unit tests
- web UI build

If the preview implementation needs one small helper module, keep it local and avoid broad refactors.

✅ Success: the implementation builds cleanly and the targeted tests pass.
❌ If failed: stop at the first real blocker and report it clearly.

---

## Execution Notes for Ptah

- Treat Home as a separate mode from the interactive session view.
- Preserve the current live session page and sidebar behavior.
- Prefer a dedicated frozen preview component over bolting preview logic into the live terminal path.
- Keep the selector inside Home only.
- Keep the terminal-looking preview colorful.
- Dispose aggressively when the user leaves Home.
