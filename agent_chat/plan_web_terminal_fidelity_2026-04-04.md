# Plan: Web Terminal Fidelity Pass
_Make the browser terminal behave like a polished xterm client: visible-first open, stable resize sync, WebGL with safe fallback, and recovery tools for visual artifacts without changing the existing visual design language._

---

# Checklist
- [x] Step 1: Add terminal renderer dependency and extend session state
- [x] Step 2: Add terminal geometry and renderer helper modules
- [x] Step 3: Refactor terminal manager for visible-first attach and controlled resize
- [x] Step 4: Refactor terminal viewport lifecycle and remove measurement-distorting padding
- [x] Step 5: Refactor websocket and session view terminal recovery flows
- [x] Step 6: Build the manager web UI and run targeted verification

---

## Context

The current browser terminal is implemented in `manager_web_ui/` with xterm.js, `@xterm/addon-fit`, and `@xterm/addon-unicode11`. The current artifact problem is caused by frontend geometry drift more than by color or layout styling.

Relevant current files:

- `manager_web_ui/src/stores/terminalManager.ts`
- `manager_web_ui/src/components/TerminalViewport.vue`
- `manager_web_ui/src/lib/websocket.ts`
- `manager_web_ui/src/views/SessionView.vue`
- `manager_web_ui/src/types/session.ts`
- `manager_web_ui/src/lib/daemonApi.ts`
- `manager_web_ui/package.json`
- `manager_web_ui/pnpm-lock.yaml`

Relevant backend files that define the current resize contract:

- `silc/api/server.py`
- `silc/core/session.py`
- `silc/core/pty_manager.py`

Current behavior to replace:

- `TerminalViewport.vue` uses a 100ms debounced `ResizeObserver` and immediately calls `manager.fit(...)`.
- `terminalManager.ts` relies on `fitAddon.fit()` plus terminal padding, which can produce non-exact geometry.
- `websocket.ts` clears and rewrites terminal history without any explicit flush or redraw control.
- No WebGL addon is loaded, no renderer fallback policy exists, and no manual recovery actions exist for texture atlas / redraw / dimension refresh.

The user explicitly asked to keep the existing visual design language. This plan only changes terminal fidelity and recovery behavior.

## Prerequisites

- Node.js version compatible with `manager_web_ui/package.json` is installed.
- `pnpm` is available because `manager_web_ui/pnpm-lock.yaml` exists.
- The repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- The executor must work from `manager_web_ui/` for frontend package commands and from repo root for anything else.
- If `pnpm install` is required after dependency edits, the executor must run it before `pnpm build`.

## Scope Boundaries

**OUT OF SCOPE:**

- Do not redesign colors, spacing systems, typography, sidebar layout, cards, or the overall visual theme.
- Do not change daemon auth, multi-client ownership semantics, or websocket ownership policy.
- Do not add a new backend websocket ack protocol in this pass.
- Do not change `silc/api/server.py`, `silc/core/session.py`, or `silc/core/pty_manager.py` unless a frontend change is impossible without a tiny contract adjustment. If a backend edit becomes necessary, stop and report instead of improvising a larger backend redesign.
- Do not touch unrelated TUI, CLI, MCP, or daemon behavior.

---

## Steps

### Step 1: Add terminal renderer dependency and extend session state

Open `manager_web_ui/package.json`.

Add the dependency `@xterm/addon-webgl` alongside the existing xterm dependencies. After editing `package.json`, run `pnpm install` in `manager_web_ui/` so `manager_web_ui/pnpm-lock.yaml` records the new dependency.

Open `manager_web_ui/src/types/session.ts`.

Extend the `Session` interface so the terminal manager can track renderer and resize lifecycle state. Add fields for all of the following:

- `webglAddon` with the correct addon type or `null`
- `rendererType` as `'dom' | 'webgl'`
- `rendererFailed` as `boolean`
- `attachEpoch` as `number`
- `pendingOpen` as `boolean`
- `pendingFitTimer` as `ReturnType<typeof setTimeout> | null`
- `pendingAnimationFrame` as `number | null`
- `lastMeasuredSize` as `{ width: number; height: number; dpr: number } | null`
- `writeInFlight` as `boolean`
- `flushWaiters` as an array of resolver callbacks

Do not remove the existing `lastSize` and `disconnectReason` fields.

✅ Success: `package.json` includes `@xterm/addon-webgl`, `pnpm-lock.yaml` changes exist, and `Session` now contains explicit renderer and resize lifecycle fields.
❌ If failed: If `pnpm install` fails or TypeScript cannot express one of the new fields, stop and report the exact error output.

---

### Step 2: Add terminal geometry and renderer helper modules

Create two new files:

- `manager_web_ui/src/lib/terminalGeometry.ts`
- `manager_web_ui/src/lib/terminalRenderer.ts`

In `manager_web_ui/src/lib/terminalGeometry.ts`, write small focused functions that do all geometry work outside the store:

1. `isElementRenderable(element: HTMLElement | null): boolean`
   - Return `false` when the element is missing, disconnected, hidden, or has zero width/height.
2. `measureContainer(element: HTMLElement): { width: number; height: number; dpr: number }`
   - Use `getBoundingClientRect()` plus `window.devicePixelRatio`.
3. `proposeTerminalGeometry(terminal: Terminal, fitAddon: FitAddon, element: HTMLElement, limits: { maxCols: number; maxRows: number }): { cols: number; rows: number; width: number; height: number; dpr: number } | null`
   - Start from `fitAddon.proposeDimensions()`.
   - Return `null` when xterm has no render dimensions yet or the container is not renderable.
   - Clamp `cols` and `rows` to the supplied limits.
   - Include the measured `width`, `height`, and `dpr` in the returned object.
4. `hasGeometryChanged(previous, next): boolean`
   - Compare rows, cols, width, height, and dpr.

In `manager_web_ui/src/lib/terminalRenderer.ts`, write small focused renderer helpers:

1. `enableRenderer(session: Session): Promise<void>`
   - Attempt to load `WebglAddon` only after `session.terminal.element` exists.
   - On success, store the addon on `session.webglAddon`, set `session.rendererType = 'webgl'`, set `session.rendererFailed = false`, and register an `onContextLoss` handler that disposes WebGL and falls back to DOM.
   - On failure, dispose any partial addon, set `session.webglAddon = null`, set `session.rendererType = 'dom'`, and set `session.rendererFailed = true`.
2. `disposeRenderer(session: Session): void`
   - Dispose `session.webglAddon` safely and clear the field.
3. `refreshRendererAfterSwap(session: Session): void`
   - Call `session.terminal.refresh(0, session.terminal.rows - 1)` when rows exist.
4. `forceTerminalRedraw(session: Session): void`
   - Call `session.terminal.clearTextureAtlas?.()` if available, then refresh the visible rows.

Do not add any design CSS in these helper files.

✅ Success: Both helper modules exist, compile, and contain only geometry / renderer responsibilities.
❌ If failed: If the addon import path or type name does not match the installed package, stop and report the exact import/type error.

---

### Step 3: Refactor terminal manager for visible-first attach and controlled resize

Open `manager_web_ui/src/stores/terminalManager.ts`.

Refactor `createSession`, `attach`, `fit`, `detach`, `removeSession`, and the write queue helpers to use the new lifecycle model.

Make all of the following changes in this file:

1. Import `WebglAddon` type from `@xterm/addon-webgl` and import the new helper functions from `@/lib/terminalGeometry` and `@/lib/terminalRenderer`.
2. In `createSession`, initialize every new `Session` field added in Step 1.
3. Keep Unicode 11 active exactly as it is today.
4. Add a new internal helper `clearPendingLayoutWork(session: Session): void` that clears `pendingFitTimer` and `pendingAnimationFrame`.
5. Add a new internal async helper `openWhenRenderable(port: number, container: HTMLElement): Promise<void>` with this exact lifecycle:
   - Increment `session.attachEpoch`.
   - If xterm has not been opened yet, wait until `container` is connected and renderable.
   - Use a short retry loop built from `requestAnimationFrame` plus a bounded `setTimeout` retry. The first open attempt must not happen until the element has visible dimensions.
   - Call `terminal.open(container)` only once per session lifetime.
   - After `open`, call `setupBrowserEventHandlers(session)`, then call `enableRenderer(session)`, then call a new store method `scheduleFit(port, { immediate: true, propagate: true, reason: 'initial-open' })`.
6. Replace the current `attach` body so re-attachment only moves the existing xterm element into the new container and then calls `scheduleFit(...)`. Do not call `terminal.open(...)` on a zero-sized or hidden container.
7. Replace the current `fit` implementation with two methods:
   - `applyMeasuredFit(port: number, options?: { propagate?: boolean; reason?: string }): Promise<void>`
   - `scheduleFit(port: number, options?: { propagate?: boolean; immediate?: boolean; reason?: string }): void`

`applyMeasuredFit` must do this exact order:

- Return early when the terminal element or parent container is not renderable.
- Call `proposeTerminalGeometry(...)`.
- Return early when geometry is `null`.
- Resize xterm first with `terminal.resize(cols, rows)` when cols or rows changed.
- Store both `lastSize` and `lastMeasuredSize` on the session.
- Only after xterm resize completes, call `resizeSession(port, rows, cols)` when `propagate !== false` and the row/col payload changed.
- If the renderer type changed recently or the measured size changed, call `refreshRendererAfterSwap(session)`.

`scheduleFit` must do this exact order:

- Cancel any pending layout work using `clearPendingLayoutWork(session)`.
- If `options.immediate === true`, schedule `applyMeasuredFit` on the next animation frame.
- Otherwise, debounce to roughly one frame budget (16ms to 34ms range is acceptable). Do not keep the previous 100ms debounce.

Add three public store methods and export them from the store return object:

- `flushWrites(port: number): Promise<void>`
- `forceRedraw(port: number): void`
- `refreshTerminalSurface(port: number): void`

Implement them exactly like this:

- `flushWrites` resolves only when `writePending === false`, `writeInFlight === false`, and `writeQueue.length === 0`.
- `forceRedraw` calls `forceTerminalRedraw(session)`.
- `refreshTerminalSurface` schedules an immediate fit with propagation enabled.

Update `processWriteQueue` so it sets `writeInFlight = true` before `terminal.write(...)`, resets `writeInFlight = false` in the callback, and resolves any pending flush waiters when the queue is empty.

Update `removeSession` and `detach` so they clear pending layout work and dispose the renderer addon safely.

✅ Success: `terminalManager.ts` no longer relies on direct `fitAddon.fit()` as the only resize mechanism, waits for visible containers before first open, exports the new recovery methods, and keeps Unicode 11 enabled.
❌ If failed: If the refactor becomes too large for one file, split pure geometry or renderer code into additional `manager_web_ui/src/lib/` modules instead of growing `terminalManager.ts` past a manageable size.

---

### Step 4: Refactor terminal viewport lifecycle and remove measurement-distorting padding

Open `manager_web_ui/src/components/TerminalViewport.vue`.

Replace the current resize lifecycle so the component delegates all sizing control to the new store methods.

Make all of the following changes:

1. Replace the current `debouncedFit` implementation with calls to `manager.scheduleFit(...)`.
2. Keep `ResizeObserver`, but do not call the old `manager.fit(...)` function anywhere in the file.
3. On mount, after `attachAndConnect()`, call `manager.scheduleFit(props.port, { immediate: true, propagate: props.interactive === true, reason: 'mounted' })`.
4. On every `ResizeObserver` callback, call `manager.scheduleFit(props.port, { propagate: props.interactive === true, reason: 'resize-observer' })`.
5. Add a `window` resize listener and a `matchMedia('(resolution: 1dppx)')`-style DPR change listener fallback that both call `manager.scheduleFit(..., { immediate: true, ... })`. If a true DPR-specific listener is not reliable in the current browser target, use `window.resize` only and stop there.
6. Keep preview terminals non-interactive. Preview terminals may fit locally, but they must not spam `/resize` when `interactive !== true`.
7. Remove or reduce extra inner padding that alters xterm geometry measurement. Specifically:
   - Remove `.terminal-bottom-gap` from the template and stylesheet.
   - Remove the extra `padding: 1px 2px` on `.terminal-host--interactive :deep(.xterm-screen)`.
   - Remove the generic `.terminal-shell :deep(.xterm-screen) { padding: 4px; }` rule.
   - Keep only the minimum wrapper styling needed for layout containment.

Do not add new visual ornaments.

✅ Success: `TerminalViewport.vue` uses the new store scheduling methods, no longer uses the 100ms debounce, and no longer injects xterm-internal padding that distorts measurement.
❌ If failed: If removing a padding rule breaks containment, keep the outer wrapper padding only and do not reintroduce padding on xterm screen elements.

---

### Step 5: Refactor websocket and session view terminal recovery flows

Open `manager_web_ui/src/lib/websocket.ts` and `manager_web_ui/src/views/SessionView.vue`.

In `manager_web_ui/src/lib/websocket.ts`, make these exact changes:

1. After `ws.onopen`, once history is requested, schedule an immediate fit through the terminal manager.
2. In the `history` message branch, before clearing and rewriting the terminal, call `manager.flushWrites(port)`.
3. After history is written, call `manager.refreshTerminalSurface(port)`.
4. In the `update` message branch, keep `manager.safeWrite(port, msg.data)`.
5. On websocket close or error, do not force a terminal reset.

In `manager_web_ui/src/views/SessionView.vue`, make these exact changes:

1. In `refreshTerminal()`, before `terminal.reset()` or `load_history`, call `await manager.flushWrites(port.value)`.
2. In `reconnectSession(...)`, before `nextSession.terminal.reset()`, call `await manager.flushWrites(targetPort)`.
3. After reconnect or history reload, call `manager.refreshTerminalSurface(targetPort)`.
4. Add two terminal recovery actions to the existing bottom control bar using the current button style classes:
   - `Refit` → calls `manager.refreshTerminalSurface(port)`
   - `Redraw` → calls `manager.forceRedraw(port)`
5. Do not change the overall visual design language of the toolbar. Only append the two new recovery actions using the existing button patterns.

✅ Success: History reloads and reconnects flush pending writes before reset/repaint, and the session view exposes `Refit` and `Redraw` recovery actions.
❌ If failed: If any reset path still clears the terminal before pending writes finish, stop and report which code path still violates the flush-first order.

---

### Step 6: Build the manager web UI and run targeted verification

From `manager_web_ui/`, run these commands in order:

```bash
pnpm build
```

If the repository already has frontend unit tests that exercise the changed modules without extra harness work, also run:

```bash
pnpm test:unit
```

If `pnpm test:unit` fails because there are no stable tests for the changed modules, report that fact explicitly and keep `pnpm build` as the required verification gate.

After the build, verify by reading the changed source files that all of the following are true:

1. `@xterm/addon-webgl` is installed and referenced.
2. The first xterm `open(...)` happens only after the container is renderable.
3. Resize is scheduled through the new measured pipeline, not the old direct `fit()` call path.
4. WebGL failure or context loss falls back to DOM without leaving the session in an unknown renderer state.
5. The session toolbar exposes `Refit` and `Redraw`.

✅ Success: `pnpm build` passes, and the source confirms the five required terminal fidelity behaviors.
❌ If failed: Report the full build error output and stop. Do not edit unrelated files to work around the error.

---

## Verification

The whole plan is complete only when all of the following are true:

1. `manager_web_ui/package.json` and `manager_web_ui/pnpm-lock.yaml` include `@xterm/addon-webgl`.
2. `manager_web_ui/src/stores/terminalManager.ts` exports visible-first resize/recovery helpers.
3. `manager_web_ui/src/components/TerminalViewport.vue` no longer contains the old 100ms resize debounce and no longer applies xterm-screen padding.
4. `manager_web_ui/src/lib/websocket.ts` flushes pending writes before history replacement and refreshes the terminal surface afterward.
5. `manager_web_ui/src/views/SessionView.vue` includes `Refit` and `Redraw` controls.
6. `pnpm build` succeeds from `manager_web_ui/`.

## Rollback

If a critical step fails and cannot be recovered, restore only the affected frontend files:

```bash
git checkout -- manager_web_ui/package.json
git checkout -- manager_web_ui/pnpm-lock.yaml
git checkout -- manager_web_ui/src/types/session.ts
git checkout -- manager_web_ui/src/stores/terminalManager.ts
git checkout -- manager_web_ui/src/components/TerminalViewport.vue
git checkout -- manager_web_ui/src/lib/websocket.ts
git checkout -- manager_web_ui/src/views/SessionView.vue
git checkout -- manager_web_ui/src/lib/terminalGeometry.ts
git checkout -- manager_web_ui/src/lib/terminalRenderer.ts
```

Then run:

```bash
pnpm build
```

from `manager_web_ui/` to confirm the rollback state builds again.
