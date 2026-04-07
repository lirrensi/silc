// FILE: tui_client/terminal_renderer.rs
// PURPOSE: Paint terminal engine state into the native TUI without leaking terminal raw bytes.
// OWNS: Screen redraws, cursor placement, and local terminal title updates.
// EXPORTS: CrosstermTerminalRenderer.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

use crate::{session_connection::ConnectionState, terminal_engine::TerminalEngine};
use crossterm::{
    cursor, execute,
    terminal::{self, Clear, ClearType},
};
use std::io::{self, Write};

type DynError = Box<dyn std::error::Error>;
type DynResult<T> = Result<T, DynError>;

pub struct CrosstermTerminalRenderer {
    last_frame: Option<String>,
    last_title: Option<String>,
}

impl CrosstermTerminalRenderer {
    pub fn new() -> Self {
        Self {
            last_frame: None,
            last_title: None,
        }
    }

    pub fn render(&mut self, engine: &dyn TerminalEngine, state: ConnectionState) -> DynResult<()> {
        let frame = engine.render_visible();
        let title = self.window_title(engine, state);

        if self.last_frame.as_deref() == Some(frame.as_str())
            && self.last_title.as_deref() == Some(title.as_str())
        {
            return Ok(());
        }

        self.last_frame = Some(frame.clone());
        self.last_title = Some(title.clone());

        let mut stdout = io::stdout();
        execute!(
            stdout,
            cursor::Hide,
            terminal::SetTitle(title),
            Clear(ClearType::All),
            cursor::MoveTo(0, 0)
        )?;
        stdout.write_all(frame.as_bytes())?;

        let cursor = engine.cursor();
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
