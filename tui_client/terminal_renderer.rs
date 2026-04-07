// FILE: tui_client/terminal_renderer.rs
// PURPOSE: Paint terminal engine state into the native TUI without leaking terminal raw bytes.
// OWNS: Cell-by-cell screen redraws, cursor placement, and local terminal title updates.
// EXPORTS: CrosstermTerminalRenderer.
// DOCS: agent_chat/plan_rust_tui_cleanup_2026-04-07.md; agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md; agent_chat/plan_tui_full_repaint_2026-04-07.md

use crate::{session_connection::ConnectionState, terminal_engine::TerminalEngine};
use crossterm::{
    cursor, queue,
    style::{Attribute, Color, ResetColor, SetAttribute, SetBackgroundColor, SetForegroundColor},
    terminal,
};
use std::io::{self, Write};
use std::time::{SystemTime, UNIX_EPOCH};

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
        session_label: &str,
    ) -> DynResult<()> {
        let title = self.window_title(engine, state);
        let cursor = engine.cursor();
        let cursor_state = (cursor.col as u16, cursor.row as u16, cursor.visible);
        let rows_to_render = 0..engine.rows();
        let footer_row = engine.rows() as u16;
        let footer_width = terminal::size()
            .map(|(cols, _)| cols as usize)
            .unwrap_or(engine.cols());
        let footer_line = self.footer_line(session_label, state, footer_width);
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

        queue!(stdout, cursor::MoveTo(0, footer_row))?;
        queue!(stdout, SetAttribute(Attribute::Reset))?;
        queue!(stdout, SetForegroundColor(Color::Grey))?;
        queue!(stdout, SetBackgroundColor(Color::DarkGrey))?;
        stdout.write_all(footer_line.as_bytes())?;
        queue!(stdout, ResetColor)?;

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

    fn footer_line(&self, session_label: &str, state: ConnectionState, width: usize) -> String {
        let state_label = match state {
            ConnectionState::Connected => "connected",
            ConnectionState::Disconnected => "disconnected",
        };
        let left = format!(" {} [{}]", session_label, state_label);
        let right = format!("Ctrl+Q detach  Ctrl+L clear  {}", clock_hint());

        if width == 0 {
            return String::new();
        }

        if right.len() >= width {
            return pad_to_width(truncate_to_width(&right, width), width);
        }

        let left_budget = width - right.len();
        let left = truncate_to_width(&left, left_budget.saturating_sub(1));
        let gap = width.saturating_sub(left.len() + right.len());

        let mut out = String::with_capacity(width);
        out.push_str(&left);
        out.extend(std::iter::repeat(' ').take(gap.max(1)));
        out.push_str(&right);
        pad_to_width(out, width)
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

fn truncate_to_width(text: &str, width: usize) -> String {
    text.chars().take(width).collect()
}

fn pad_to_width(mut text: String, width: usize) -> String {
    let current = text.chars().count();
    if current < width {
        text.extend(std::iter::repeat(' ').take(width - current));
    }
    text
}

fn clock_hint() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let day_seconds = seconds % 86_400;
    let hours = day_seconds / 3_600;
    let minutes = (day_seconds % 3_600) / 60;
    format!("UTC {hours:02}:{minutes:02}")
}
