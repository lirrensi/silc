# Plan: Hidden Live CWD Prompt Prototype
_Done means a shell can emit a hidden CWD marker on prompt redraw, SILC captures it from the PTY stream, and the session view shows the live directory without visible junk in the terminal output._

---

# Checklist
- [x] Step 1: Add an OSC parser for hidden CWD markers
- [x] Step 2: Teach SilcSession to track and broadcast cwd changes
- [x] Step 3: Emit the hidden marker from PowerShell prompt hooks
- [x] Step 4: Pipe cwd updates through daemon/API/websocket into the web UI
- [x] Step 5: Add focused tests for parsing and live propagation
- [x] Step 6: Run targeted verification

---

## Context
- The current shell session logic lives in `silc/core/session.py`.
- OSC title parsing already exists in `silc/core/osc.py`.
- PowerShell shell helper injection already exists in `silc/utils/shell_detect.py`.
- The per-session websocket already broadcasts title updates from `silc/api/server.py`.
- The daemon session list already carries `cwd` through `silc/daemon/manager.py`.
- The manager web UI already renders `session.cwd` in the session header and sidebar, but it only updates from daemon data today.

## Prerequisites
- Repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- Prototype scope only: keep the first pass focused on PowerShell and the existing PTY path.
- Do not change unrelated shell execution or websocket framing behavior.

## Scope Boundaries
- Do not add a visible prompt prefix or any raw debug text to the shell output.
- Do not change session command execution semantics.
- Do not expand to every shell type unless it falls out naturally from the same helper shape.
- Do not update docs unless the implementation settles enough to justify canon sync later.

---

## Steps

### Step 1: Add an OSC parser for hidden CWD markers
Open `silc/core/osc.py` and add a small parser for a hidden CWD marker sequence.

Make the parser accept OSC payloads emitted by the prompt hook, with a marker shaped like `633;cwd=<encoded-path>` terminated by BEL or ST.
Keep the existing title parser intact.

Use a decoding strategy that is safe for paths with spaces and special characters. Prefer URL-encoded or similarly reversible encoding over raw path text.

✅ Success: the parser can extract a cwd string from an OSC payload without exposing the marker as visible text.
❌ If failed: remove the new parser and stop. Do not continue with a half-parsed marker format.

### Step 2: Teach SilcSession to track and broadcast cwd changes
Open `silc/core/session.py` and add cwd tracking parallel to the existing title tracking.

Implement these exact behaviors:
1. Feed the new OSC parser from the PTY read loop.
2. When a cwd marker changes, update `self.cwd`.
3. Add a cwd-change callback/listener path so daemon code can persist the new cwd.
4. Include the live cwd in `get_status()` so API callers can see the latest value.
5. Keep the cwd marker out of rendered output/history views.

Reuse the existing title-update pattern where it fits; do not invent a second unrelated runtime channel if a listener is enough.

✅ Success: a session can update its cwd in memory as soon as the prompt marker is read.
❌ If failed: revert the session changes and stop. Do not leave cwd updates partially wired.

### Step 3: Emit the hidden marker from PowerShell prompt hooks
Open `silc/utils/shell_detect.py` and update the PowerShell helper text so the shell emits a hidden cwd marker from `prompt`.

Requirements:
1. The marker must not print visible text into the terminal.
2. The marker should run on every prompt redraw so `cd` is reflected quickly.
3. The existing `__silc_exec` helper must keep working.
4. Prefer the prompt hook only for PowerShell in this first prototype.

Use the same marker format that Step 1 parses.

✅ Success: the PowerShell helper prints a hidden cwd marker and still leaves the visible prompt clean.
❌ If failed: revert the helper text change and stop. Do not contaminate the shell output.

### Step 4: Pipe cwd updates through daemon/API/websocket into the web UI
Open `silc/daemon/manager.py`, `silc/api/server.py`, `manager_web_ui/src/lib/websocket.ts`, and `manager_web_ui/src/stores/terminalManager.ts`.

Wire the live cwd value through the existing session update path:
1. Persist cwd changes back into the daemon registry/session record.
2. Expose live cwd in daemon list/status responses so refreshes show the current folder.
3. Send a websocket frame when cwd changes, similar to title updates.
4. Add a store method to update the local session cwd from websocket events.
5. Leave the current `session.cwd` rendering in `SessionView.vue` and the sidebar in place.

✅ Success: the web UI can receive and show cwd changes without refreshing the whole app.
❌ If failed: revert only the live-cwd propagation changes and stop. Do not leave a broken websocket event type in place.

### Step 5: Add focused tests for parsing and live propagation
Add or update targeted tests under `tests/`.

Cover at least:
1. The new OSC parser extracts cwd from BEL/ST-terminated payloads.
2. The PowerShell helper text contains the hidden cwd emission path.
3. A session status payload includes the live cwd field.
4. The websocket client/store accepts a cwd update frame.

Keep tests narrow and prototype-friendly.

✅ Success: the tests prove the hidden-marker approach is captured by SILC and stays invisible in normal output.
❌ If failed: revert the new/updated tests and stop.

### Step 6: Run targeted verification
Run focused checks from the repository root:
1. Python tests touching OSC/session/daemon paths.
2. Frontend tests or typecheck covering the websocket/store change.

If a failure is caused by this prototype, fix only the smallest relevant code path and rerun the same command.

✅ Success: the targeted tests pass, or they fail in a way that cleanly proves the prototype still needs deeper PTY integration.
❌ If failed: capture the exact command and output, fix the prototype scope only, and rerun.

---

## Verification
- Hidden cwd markers are parsed but not rendered as shell text.
- Session cwd changes follow prompt redraws.
- Daemon/session list responses reflect live cwd after it changes.
- The web UI shows the current cwd beside the shell.

## Rollback
- If the prototype gets messy, revert the touched files back to HEAD and leave only this plan file behind.
