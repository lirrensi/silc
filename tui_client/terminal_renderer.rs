// FILE: tui_client/terminal_renderer.rs
// PURPOSE: Paint terminal engine state into the native TUI without leaking terminal raw bytes.
// OWNS: Screen redraws, cursor placement, and local terminal title updates.
// EXPORTS: CrosstermTerminalRenderer.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

use crate::{session_connection::ConnectionState, terminal_engine::TerminalEngine};
use crossterm::{cursor, execute, terminal};
use std::io::{self, Write};

type DynError = Box<dyn std::error::Error>;
type DynResult<T> = Result<T, DynError>;

pub struct CrosstermTerminalRenderer {
    last_frame: Option<String>,
    last_title: Option<String>,
    last_cursor: Option<(u16, u16, bool)>,
}

impl CrosstermTerminalRenderer {
    pub fn new() -> Self {
        Self {
            last_frame: None,
            last_title: None,
            last_cursor: None,
        }
    }

    pub fn reset(&mut self) {
        self.last_frame = None;
        self.last_title = None;
        self.last_cursor = None;
    }

    pub fn render(&mut self, engine: &dyn TerminalEngine, state: ConnectionState) -> DynResult<()> {
        let frame = engine.render_visible();
        let title = self.window_title(engine, state);
        let cursor = engine.cursor();
        let cursor_state = (cursor.col as u16, cursor.row as u16, cursor.visible);

        if self.last_frame.as_deref() == Some(frame.as_str())
            && self.last_title.as_deref() == Some(title.as_str())
            && self.last_cursor == Some(cursor_state)
        {
            return Ok(());
        }

        let mut stdout = io::stdout();
        execute!(stdout, cursor::Hide, terminal::SetTitle(title.clone()))?;

        stdout.write_all(frame.as_bytes())?;

        if cursor.visible {
            execute!(
                stdout,
                cursor::MoveTo(cursor.col as u16, cursor.row as u16),
                cursor::Show
            )?;
        } else {
            execute!(stdout, cursor::Hide)?;
        }

        stdout.flush()?;

        self.last_frame = Some(frame);
        self.last_title = Some(title);
        self.last_cursor = Some(cursor_state);

        Ok(())
    }

    fn window_title(&self, engine: &dyn TerminalEngine, state: ConnectionState) -> String {
        let title_text = engine.title();
        let base = if let Some(cwd) = engine.current_directory() {
            if title_text.trim().is_empty() {
                cwd
            } else {
                format!("{} — {}", title_text.trim(), cwd)
            }
        } else if title_text.trim().is_empty() {
            "SILC".to_string()
        } else {
            title_text.trim().to_string()
        };

        match state {
            ConnectionState::Connected => base,
            ConnectionState::Disconnected => format!("{base} [disconnected]"),
        }
    }
}
