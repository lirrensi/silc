# Plan: Manager QoL rename + reorder + default titles

## Goal
Add two user-facing quality-of-life features to the manager UI and daemon:

1. Rename sessions interactively from the web UI.
2. Reorder sessions visually and persist that order.
3. Seed new sessions with a sensible initial title based on the shell name/label until the shell publishes its own title.

## Decisions locked
- Rename is canonical: it updates the real session name used everywhere.
- Keep the existing name validation rule.
- Reject duplicate names hard.
- Reorder is functional, not just cosmetic: persist the chosen order and serve it back in that order.
- Use `@dnd-kit/vue` for Vue 3 drag/reorder.
- For multi-tab sync, emit a daemon event and have clients refresh/reconcile the full session list immediately.
- Do not broaden the locking refactor in this pass.

## Backend work
1. Add daemon endpoints:
   - `POST /sessions/{port}/rename`
   - `POST /sessions/reorder`
2. Extend the registry so sessions can be reordered without port sorting.
3. Persist the reordered session list to `sessions.json` in the chosen order.
4. Update initial session title creation so the shell label/name is used before OSC updates arrive.
5. Broadcast daemon events for rename/reorder so other tabs refresh immediately.
6. Keep port safety intact: rename must never touch the port or port-based lifecycle.

## Frontend work
1. Add a simple `window.prompt()` rename flow on double click.
2. Preflight duplicate-name checks in the UI for quick feedback, but still rely on the backend for enforcement.
3. Add drag-and-drop reordering with `@dnd-kit/vue` in the manager list.
4. Stop sorting the rendered session list by port; preserve backend order.
5. Make list reconciliation preserve incoming order so reorder is visible across tabs.
6. Ensure live daemon events refresh the full list immediately after reorder.

## Tests
- Backend: duplicate-name rejection, rename persistence, reorder persistence, event broadcast.
- Frontend: rename prompt behavior, duplicate-name guard, reorder reconciliation, multi-tab refresh path.

## Verification
- Run the targeted backend tests for daemon registry/manager behavior.
- Run the manager UI unit tests and build.
- Confirm rename and reorder both update a second client view without manual refresh.
