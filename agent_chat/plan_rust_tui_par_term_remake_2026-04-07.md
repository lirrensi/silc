# Plan: remake Rust TUI on par-term core

## Goal
Replace the current raw websocket-to-stdout Rust TUI with a real terminal-emulation core so pwsh/zsh behave the same way they do in the web xterm path.

## Decision
- Use `par-term-emu-core-rust` as the live screen/state engine.
- Keep the existing websocket/session protocol unchanged.
- Keep Python snapshot rendering on the current engine for now.

## Architecture boundary
- `SessionConnection`: owns websocket/PTY transport, resize, takeover, and input forwarding.
- `TerminalEngine`: owns parsing/render state and screen updates.
- `TerminalRenderer`: owns painting the engine state to the Rust UI.
- The engine must be swappable so `alacritty_terminal` can replace `par-term` later if needed.

## In scope
- Parse incoming PTY bytes through a real terminal model.
- Render the terminal surface in the Rust TUI.
- Preserve resize, paste, keyboard, and mouse input handling.
- Remove ad-hoc query-noise stripping from the render path.

## Out of scope
- Changing daemon/session PTY behavior.
- Changing the websocket protocol.
- Adding triggers/graphics/recording features in v1 unless they fall out naturally from the engine API.
- Rewriting the Python snapshot pipeline.

## Implementation steps
1. Introduce the `TerminalEngine` abstraction behind the current Rust client.
2. Swap the Rust client from “print bytes” to “feed bytes into terminal model, then paint screen”.
3. Add a renderer for the visible grid, scrollback, cursor, and selection state.
4. Wire keyboard input, paste, mouse, and resize into terminal-compatible escape sequences.
5. Keep session title/cwd updates as metadata, not as display hacks.
6. Delete the brittle DA/query filtering once the emulator path is active.
7. Validate pwsh, zsh, alternate screen apps, resize, copy/paste, and mouse behavior.

## Risks / watch-outs
- `par-term` may expose more features, but the Rust UI still needs a paint loop.
- Mouse support depends on correct terminal-mode negotiation and input translation.
- Some xterm quirks may still differ; expect fidelity, not perfect identity.

## Fallback path
- If `par-term` becomes too noisy or unstable, swap only the `TerminalEngine` implementation.
- Keep `SessionConnection` and `TerminalRenderer` unchanged so the migration to `alacritty_terminal` is local.

## Verification
- `cargo check` in `tui_client/`
- manual smoke test with `pwsh`, `zsh`, and a mouse-aware app
- confirm no literal `ESC[?1;2c` leakage on login

## Success criteria
- Rust TUI looks and behaves like a real terminal.
- Shell startup/output is clean.
- No special-case query bytes leak into the UI.
- Basic mouse and resize work without breaking interactive shells.

## Status
- [x] Implementation steps 1-7 completed in tui_client/
