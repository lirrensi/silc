// FILE: tui_client/terminal_renderer.rs
// PURPOSE: Paint terminal engine state into the native TUI without leaking terminal raw bytes.
// OWNS: Cell-by-cell screen redraws, cursor placement, and local terminal title updates.
// EXPORTS: CrosstermTerminalRenderer.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md; agent_chat/plan_tui_full_repaint_2026-04-07.md

use crate::{session_connection::ConnectionState, terminal_engine::TerminalEngine};
use crossterm::{
    cursor, queue,
    style::{Attribute, Color, SetAttribute, SetBackgroundColor, SetForegroundColor},
    terminal,
};
use std::io::{self, Write};

type DynError = Box<dyn std::error::Error>;
type DynResult<T> = Result<T, DynError>;

pub struct CrosstermTerminalRenderer {
    last_title: Option<String>,
    last_cursor: Option<(u16, u16, bool)>,
    force_full_refresh: bool,
}

impl CrosstermTerminalRenderer {
    pub fn new() -> Self {
        Self {
            last_title: None,
            last_cursor: None,
            force_full_refresh: true,
        }
    }

    pub fn reset(&mut self) {
        self.last_title = None;
        self.last_cursor = None;
        self.force_full_refresh = true;
    }

    pub fn render(
        &mut self,
        engine: &mut dyn TerminalEngine,
        state: ConnectionState,
    ) -> DynResult<()> {
        let title = self.window_title(engine, state);
        let cursor = engine.cursor();
        let cursor_state = (cursor.col as u16, cursor.row as u16, cursor.visible);
        let rows_to_render = (0..engine.rows()).collect::<Vec<_>>();
        if self.force_full_refresh {
            self.force_full_refresh = false;
        }

        if rows_to_render.is_empty()
            && self.last_title.as_deref() == Some(title.as_str())
            && self.last_cursor == Some(cursor_state)
        {
            return Ok(());
        }

        let mut stdout = io::stdout();
        queue!(stdout, cursor::Hide)?;

        if self.last_title.as_deref() != Some(title.as_str()) {
            queue!(stdout, terminal::SetTitle(title.clone()))?;
        }

        for row in rows_to_render {
            queue!(stdout, cursor::MoveTo(0, row as u16))?;

            for col in 0..engine.cols() {
                let Some(cell) = engine.cell(row, col) else {
                    queue!(stdout, SetAttribute(Attribute::Reset))?;
                    stdout.write_all(b" ")?;
                    continue;
                };

                queue!(stdout, SetAttribute(Attribute::Reset))?;
                queue!(stdout, SetForegroundColor(par_term_color(cell.fg)))?;
                queue!(stdout, SetBackgroundColor(par_term_color(cell.bg)))?;

                if cell.flags.wide_char_spacer() {
                    stdout.write_all(b" ")?;
                    continue;
                }

                if cell.flags.bold() {
                    queue!(stdout, SetAttribute(Attribute::Bold))?;
                }
                if cell.flags.dim() {
                    queue!(stdout, SetAttribute(Attribute::Dim))?;
                }
                if cell.flags.italic() {
                    queue!(stdout, SetAttribute(Attribute::Italic))?;
                }
                if cell.flags.underline() {
                    queue!(stdout, SetAttribute(Attribute::Underlined))?;
                }
                if cell.flags.blink() {
                    queue!(stdout, SetAttribute(Attribute::SlowBlink))?;
                }
                if cell.flags.reverse() {
                    queue!(stdout, SetAttribute(Attribute::Reverse))?;
                }
                if cell.flags.hidden() {
                    queue!(stdout, SetAttribute(Attribute::Hidden))?;
                }
                if cell.flags.strikethrough() {
                    queue!(stdout, SetAttribute(Attribute::CrossedOut))?;
                }

                let text = cell.get_grapheme();
                let glyph = if text.is_empty() { " " } else { text.as_str() };
                stdout.write_all(glyph.as_bytes())?;
            }
        }

        if cursor.visible {
            queue!(
                stdout,
                cursor::MoveTo(cursor.col as u16, cursor.row as u16),
                cursor::Show
            )?;
        } else {
            queue!(stdout, cursor::Hide)?;
        }

        stdout.flush()?;
        self.last_title = Some(title);
        self.last_cursor = Some(cursor_state);
        engine.mark_clean();

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

fn par_term_color(color: par_term_emu_core_rust::color::Color) -> Color {
    let (r, g, b) = color.to_rgb();
    Color::Rgb { r, g, b }
}
