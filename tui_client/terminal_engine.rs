// FILE: tui_client/terminal_engine.rs
// PURPOSE: Wrap the par-term terminal core behind a swappable terminal-emulation boundary.
// OWNS: PTY byte ingestion, render-state access, resize handling, and terminal-mode queries.
// EXPORTS: TerminalEngine, ParTermEngine.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

use par_term_emu_core_rust::{
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
    fn render_visible(&self) -> String;
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

    fn render_visible(&self) -> String {
        self.terminal.export_visible_screen_styled()
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
