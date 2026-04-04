# Plan: Binary WebSocket Framing
_Done means the session websocket uses a binary envelope of `[4-byte big-endian header length][JSON header UTF-8 bytes][raw payload bytes]` for both directions, and both the web UI and native Rust TUI speak that protocol without a compatibility layer._

---

# Checklist
- [ ] Step 1: Add shared websocket frame helpers in the Python server
- [ ] Step 2: Replace server websocket send and receive paths with framed binary messages
- [ ] Step 3: Replace web UI websocket parsing and sending with framed binary messages
- [ ] Step 4: Replace Rust TUI websocket parsing and sending with framed binary messages
- [ ] Step 5: Update architecture docs for the framed websocket protocol
- [ ] Step 6: Run focused verification for Python, web UI, and Rust TUI

---

## Context
- The current websocket implementation lives in `silc/api/server.py`.
- The current server sends JSON text frames for `update`, `history`, and `title`, and receives JSON text frames for `type` and `load_history`.
- The web UI websocket client lives in `manager_web_ui/src/lib/websocket.ts` and writes terminal bytes through `manager_web_ui/src/stores/terminalManager.ts`.
- The web UI currently expects JSON text messages and sends JSON text messages.
- The native Rust TUI client lives in `tui_client/main.rs`.
- The native Rust TUI currently expects JSON text `update` messages, accepts raw binary as a passthrough fallback, and sends JSON text `type` messages.
- Architecture canon describing the current websocket behavior lives in `docs/arch_api.md` and `docs/arch_webui.md`.

## Prerequisites
- Repository root is `C:\Users\rx\001_Code\100_M\SILC`.
- Python environment and project dependencies are already installed well enough to run repository tests.
- Node dependencies for `manager_web_ui/` are already installed.
- Rust toolchain is already installed well enough to run `cargo check` inside `tui_client/`.
- No backward compatibility is required. Every websocket client in this repository must move to the new framing in the same change.

## Scope Boundaries
- Do not change REST endpoint behavior in `silc/api/server.py` outside websocket-specific code.
- Do not change PTY read semantics in `silc/core/session.py` or `silc/core/raw_buffer.py` during this plan.
- Do not add a dual-protocol compatibility layer.
- Do not change the daemon manager or session lifecycle code outside what is strictly needed for websocket framing.
- Do not edit built artifacts under `static/`.

---

## Steps

### Step 1: Add shared websocket frame helpers in the Python server
Open `silc/api/server.py`. Add small focused helper functions near the websocket code that:
1. Encode an outbound websocket frame from a JSON header dictionary and a `bytes` payload.
2. Decode an inbound websocket frame from `bytes` into a parsed JSON header dictionary and a `bytes` payload.
3. Validate that the first 4 bytes are a big-endian unsigned header length.
4. Validate that the frame contains at least `4 + header_length` bytes.
5. Decode the header bytes as UTF-8 and parse them as JSON.
6. Raise a controlled `ValueError` with a short explicit message for malformed frames.

Use the message type key `type` in the JSON header, not `event`.

✅ Success: `silc/api/server.py` contains reusable helpers for `encode_ws_frame(...)` and `decode_ws_frame(...)` or equivalently named helpers, and the helpers operate on raw `bytes` plus parsed header dictionaries.
❌ If failed: remove the partial helper code from `silc/api/server.py`, restore the file to the last working state, and stop. Do not continue to Step 2 with inline ad-hoc framing logic.

### Step 2: Replace server websocket send and receive paths with framed binary messages
Open `silc/api/server.py`. Replace the websocket implementation so that all application messages on `/ws` use binary frames encoded by the Step 1 helpers.

Make these exact protocol changes:
1. `send_updates()` must send frames with JSON header `{"type": "output"}` and raw PTY bytes as the payload. Do not decode PTY bytes to text before sending.
2. The `load_history` response must send a frame with JSON header `{"type": "history"}` and `session.buffer.get_bytes()` as the raw payload.
3. Title notifications must send a frame with JSON header containing `{"type": "title", "title": <title>, "title_updated_at": <iso timestamp>}` and an empty payload.
4. Incoming websocket messages must be received as raw bytes, decoded with the Step 1 helper, and dispatched by `header["type"]`.
5. Input messages must use JSON header `{"type": "input", "nonewline": <bool>}` with the user input bytes in the payload.
6. History requests must use JSON header `{"type": "load_history"}` with an empty payload.
7. For malformed frames or unsupported message types, close the websocket with a protocol error code and a short reason string. Do not silently ignore malformed frames.
8. Keep the single-active-websocket behavior, title listener registration, and cleanup behavior unchanged apart from the framing changes.

Do not leave any `send_json`, `receive_text`, or JSON-string websocket protocol logic in the `/ws` path after this step.

✅ Success: `/ws` in `silc/api/server.py` uses only binary websocket send/receive for application frames, `output` and `history` ship raw bytes, and `input` arrives as payload bytes instead of JSON text fields.
❌ If failed: revert the websocket endpoint in `silc/api/server.py` to the pre-step state, keep the Step 1 helpers if they are correct and isolated, and stop. Do not proceed with mixed text/binary protocol behavior.

### Step 3: Replace web UI websocket parsing and sending with framed binary messages
Open `manager_web_ui/src/lib/websocket.ts`. Add client-side frame helpers that mirror the server protocol exactly:
1. Encode a frame from a JSON header object and an optional `Uint8Array` payload.
2. Decode an incoming `ArrayBuffer` into a parsed JSON header and payload bytes.

Then replace the websocket flow in `manager_web_ui/src/lib/websocket.ts` with this exact behavior:
1. Set `ws.binaryType = 'arraybuffer'` immediately after constructing the websocket.
2. On open, send a framed binary message with header `{"type": "load_history"}` and no payload.
3. On message, require binary data, decode the frame, branch on `header.type`, and handle:
   - `history`: flush queued writes, clear the terminal, write the payload bytes to xterm, flush writes again, refresh the terminal surface, resolve history refresh waiters.
   - `output`: write the payload bytes directly to xterm through the terminal manager.
   - `title`: update title metadata from the header and ignore the empty payload.
4. Remove the old JSON parsing branch and the old text fallback branch.
5. Replace every outgoing terminal input send in `manager_web_ui/src/lib/websocket.ts` with framed binary messages using header `{"type": "input", "nonewline": true}` and UTF-8 encoded payload bytes.

Open `manager_web_ui/src/stores/terminalManager.ts` and change terminal write buffering so terminal writes accept `Uint8Array` chunks instead of string chunks. Preserve ordering, flush semantics, and queue-draining behavior. Use xterm APIs that accept binary-safe data without converting PTY bytes through a JavaScript string first.

Open `manager_web_ui/src/views/SessionView.vue` and replace direct websocket JSON sends in `refreshTerminal()` and `sendViaWs()` with the new framed helper functions from `manager_web_ui/src/lib/websocket.ts`.

✅ Success: the web UI no longer sends or expects JSON text websocket application messages, and xterm receives history/output as raw byte buffers.
❌ If failed: revert websocket message handling in `manager_web_ui/src/lib/websocket.ts`, `manager_web_ui/src/stores/terminalManager.ts`, and `manager_web_ui/src/views/SessionView.vue` to the pre-step state, then stop. Do not proceed with partial client migration.

### Step 4: Replace Rust TUI websocket parsing and sending with framed binary messages
Open `tui_client/main.rs`. Add Rust helpers that mirror the new frame format exactly:
1. Encode a frame from a serializable header and a byte payload.
2. Decode a websocket binary message into a parsed JSON header value and payload bytes.

Then replace the native TUI websocket flow in `tui_client/main.rs` with this exact behavior:
1. The websocket reader must expect binary websocket messages for all application frames.
2. `output` frames must forward the raw payload bytes to `tx_output`.
3. `history` frames must also forward the raw payload bytes to `tx_output`.
4. `title` frames may be parsed and ignored if the native TUI has no title display path.
5. Remove the old JSON text `update` protocol handling.
6. The websocket writer must send framed binary messages with header `{"type": "input", "nonewline": true}` and the raw input bytes as the payload.
7. After the websocket connection opens, send a framed binary `load_history` request with an empty payload so the initial terminal contents come through the websocket protocol.

Keep the existing HTTP `/raw`, `/clear`, and `/resize` behavior unchanged unless a compile error forces a minimal local refactor. If a minimal local refactor is required, keep behavior identical.

✅ Success: `tui_client/main.rs` no longer depends on JSON text websocket application frames and uses framed binary messages for history, output, and input.
❌ If failed: revert `tui_client/main.rs` to the pre-step websocket logic and stop. Do not continue with a mixed protocol.

### Step 5: Update architecture docs for the framed websocket protocol
Open `docs/arch_api.md` and replace the websocket protocol section so it documents the framed binary message format, the `type` header field, the `output`, `history`, `title`, `input`, and `load_history` message types, and the rule that PTY output bytes are transmitted without UTF-8 decoding in the server.

Open `docs/arch_webui.md` and replace the web UI websocket manager section so it documents the same framed binary protocol, including `binaryType = 'arraybuffer'`, binary parsing on receive, and binary-safe terminal writes.

Keep the docs aligned with the implementation from Steps 2 through 4. Do not document compatibility behavior that does not exist.

✅ Success: `docs/arch_api.md` and `docs/arch_webui.md` describe the new framed binary websocket protocol and no longer describe the old JSON `event`/`data` message format.
❌ If failed: revert both architecture documents to the pre-step content and stop. Do not leave the docs in a half-migrated state.

### Step 6: Run focused verification for Python, web UI, and Rust TUI
Run these commands from the repository root unless a different working directory is stated:
1. `pytest tests/`
2. In `manager_web_ui/`: run the project validation command used for this frontend. Prefer the repository-standard test command if defined in `manager_web_ui/package.json`. At minimum run the unit test suite and a TypeScript-capable build or type check.
3. In `tui_client/`: run `cargo check`.

If a command fails because the protocol rename broke tests or type checks, fix only the code necessary to make the new websocket framing implementation pass. Do not broaden scope.

✅ Success: Python tests pass, web UI validation passes, and `cargo check` passes for `tui_client/`.
❌ If failed: capture the failing command and output, fix the exact failure if it is caused by this plan, rerun the same command, and stop only if the failure is unrelated or cannot be resolved without expanding scope.

---

## Verification
- `silc/api/server.py` contains no `/ws`-path use of `send_json` or `receive_text`.
- `manager_web_ui/src/lib/websocket.ts` sets `binaryType = 'arraybuffer'` and decodes incoming `ArrayBuffer` frames.
- `manager_web_ui/src/stores/terminalManager.ts` accepts binary-safe terminal writes rather than string-only websocket data.
- `tui_client/main.rs` sends and receives websocket binary frames with framed headers.
- `docs/arch_api.md` and `docs/arch_webui.md` match the shipped protocol.
- `pytest tests/` passes.
- Web UI validation passes.
- `cargo check` in `tui_client/` passes.

## Rollback
- If the implementation cannot be stabilized, revert the modified files to the repository HEAD state with:
  - `git checkout -- silc/api/server.py`
  - `git checkout -- manager_web_ui/src/lib/websocket.ts`
  - `git checkout -- manager_web_ui/src/stores/terminalManager.ts`
  - `git checkout -- manager_web_ui/src/views/SessionView.vue`
  - `git checkout -- tui_client/main.rs`
  - `git checkout -- docs/arch_api.md docs/arch_webui.md`
- After rollback, run `git status` and confirm that only `agent_chat/plan_ws_binary_framing_2026-04-05.md` remains changed.
