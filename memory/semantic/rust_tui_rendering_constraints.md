---
summary: "Current durable constraints for SILC Rust TUI rendering correctness and visual stability"
created: 2026-04-07
updated: 2026-04-07
memory_type: semantic
tags: [code, rust, tui, terminal, rendering, constraints, par-term]
---

# Rust TUI rendering constraints

## Current truth

- The Rust TUI uses `par-term-emu-core-rust` as the terminal emulation core, but the host-terminal painting policy is owned by `tui_client/terminal_renderer.rs`.
- The web client being correct does not prove the Rust renderer is correct, because xterm combines emulation and rendering while the Rust TUI splits them.
- For this codebase, `dirty_rows()` is not a reliable enough source of truth for repaint decisions in the native TUI.
- Full visible-grid repaint per render is the current stable baseline for correctness.
- Per-row `ClearType::UntilNewLine` causes visible flicker during typing when combined with full-frame repaint and should remain disabled.
- Wide-char spacer cells must be painted as spaces or host-terminal leftovers can remain visible.
- RGB color conversion from par-term colors is safer than mapping named colors through terminal palette assumptions.

## Files that matter

- `tui_client/terminal_renderer.rs`
- `tui_client/terminal_engine.rs`
- `docs/arch_tui.md`

## Warning for future changes

If shadows ever reappear, first check whether someone reintroduced dirty-row-driven rendering or row-clearing behavior before assuming the websocket/session/backend path is broken.
