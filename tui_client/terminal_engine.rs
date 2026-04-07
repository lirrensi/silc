// FILE: tui_client/terminal_engine.rs
// PURPOSE: Wrap the par-term terminal core behind a swappable terminal-emulation boundary.
// OWNS: PTY byte ingestion, screen-state access, resize handling, and terminal-mode queries.
// EXPORTS: TerminalEngine, ParTermEngine.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

use par_term_emu_core_rust::{
    cell::Cell,
    cursor::Cursor,
    mouse::{MouseEvent, MouseMode},
    terminal::Terminal,
};

pub trait TerminalEngine {
    fn resize(&mut self, cols: usize, rows: usize);
    fn reset(&mut self);
    fn process_output(&mut self, data: &[u8]);
    fn drain_responses(&mut self) -> Vec<u8>;
    fn paste(&mut self, text: &str);
    fn report_mouse(&mut self, event: MouseEvent) -> Vec<u8>;
    fn report_focus_in(&self) -> Vec<u8>;
    fn report_focus_out(&self) -> Vec<u8>;
    fn rows(&self) -> usize;
    fn cols(&self) -> usize;
    fn dirty_rows(&self) -> Vec<usize>;
    fn mark_clean(&mut self);
    fn cell(&self, row: usize, col: usize) -> Option<&Cell>;
    fn cursor(&self) -> Cursor;
    fn title(&self) -> String;
    fn current_directory(&self) -> Option<String>;
    fn mouse_mode(&self) -> MouseMode;
}

pub struct ParTermEngine {
    terminal: Terminal,
}

impl ParTermEngine {
    pub fn new(cols: usize, rows: usize) -> Self {
        Self {
            terminal: Terminal::new(cols, rows),
        }
    }
}

impl TerminalEngine for ParTermEngine {
    fn resize(&mut self, cols: usize, rows: usize) {
        self.terminal.resize(cols, rows);
    }

    fn reset(&mut self) {
        self.terminal.reset();
    }

    fn process_output(&mut self, data: &[u8]) {
        self.terminal.process(data);
    }

    fn drain_responses(&mut self) -> Vec<u8> {
        self.terminal.drain_responses()
    }

    fn paste(&mut self, text: &str) {
        self.terminal.paste(text);
    }

    fn report_mouse(&mut self, event: MouseEvent) -> Vec<u8> {
        self.terminal.report_mouse(event)
    }

    fn report_focus_in(&self) -> Vec<u8> {
        self.terminal.report_focus_in()
    }

    fn report_focus_out(&self) -> Vec<u8> {
        self.terminal.report_focus_out()
    }

    fn rows(&self) -> usize {
        self.terminal.active_grid().rows()
    }

    fn cols(&self) -> usize {
        self.terminal.active_grid().cols()
    }

    fn dirty_rows(&self) -> Vec<usize> {
        self.terminal.get_dirty_rows()
    }

    fn mark_clean(&mut self) {
        self.terminal.mark_clean();
    }

    fn cell(&self, row: usize, col: usize) -> Option<&Cell> {
        self.terminal
            .active_grid()
            .row(row)
            .and_then(|cells| cells.get(col))
    }

    fn cursor(&self) -> Cursor {
        *self.terminal.cursor()
    }

    fn title(&self) -> String {
        self.terminal.title().to_string()
    }

    fn current_directory(&self) -> Option<String> {
        self.terminal.current_directory().map(ToOwned::to_owned)
    }

    fn mouse_mode(&self) -> MouseMode {
        self.terminal.mouse_mode()
    }
}
