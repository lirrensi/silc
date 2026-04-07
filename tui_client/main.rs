// FILE: tui_client/main.rs
// PURPOSE: Orchestrate the native SILC TUI by wiring session transport, terminal emulation, and rendering.
// OWNS: Process startup, event-loop coordination, and high-level session lifecycle.
// EXPORTS: main - launch the standalone TUI client binary.
// DOCS: agent_chat/plan_rust_tui_cleanup_2026-04-07.md; agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

mod session_connection;
mod terminal_engine;
mod terminal_renderer;

use crate::{
    session_connection::{request_clear, request_resize, ConnectionState, SessionConnection},
    terminal_engine::{ParTermEngine, TerminalEngine},
    terminal_renderer::CrosstermTerminalRenderer,
};
use crossterm::{
    cursor,
    event::{
        self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEventKind,
    },
    execute,
    terminal::{self, Clear, ClearType},
};
use serde::Deserialize;
use std::{
    io::{self, Write},
    sync::Arc,
    thread,
    time::Duration,
};
use tokio::sync::mpsc;
use ureq::Agent;
use url::Url;

type DynError = Box<dyn std::error::Error>;
type DynResult<T> = Result<T, DynError>;

#[derive(Debug, Deserialize)]
struct SessionStatus {
    name: String,
    port: u16,
    title: String,
}

enum UiEvent {
    Input(Event),
    Tick,
}

struct TerminalGuard {
    restored: bool,
}

impl TerminalGuard {
    fn enter() -> DynResult<Self> {
        terminal::enable_raw_mode()?;
        Ok(Self { restored: false })
    }

    fn restore(&mut self) {
        if self.restored {
            return;
        }
        self.restored = true;

        let _ = terminal::disable_raw_mode();
    }
}

impl Drop for TerminalGuard {
    fn drop(&mut self) {
        self.restore();
    }
}

fn ws_to_http_base(ws_url: &Url) -> Url {
    let mut http = ws_url.clone();

    let _ = http.set_scheme(match ws_url.scheme() {
        "ws" => "http",
        "wss" => "https",
        other => other,
    });

    http.set_path("/");
    http.set_query(None);
    http.set_fragment(None);
    http
}

fn clear_local_screen() -> DynResult<()> {
    let mut stdout = io::stdout();
    execute!(stdout, Clear(ClearType::All), cursor::MoveTo(0, 0))?;
    stdout.flush()?;
    Ok(())
}

fn content_rows_for_terminal(rows: u16) -> u16 {
    rows.saturating_sub(1)
}

fn session_label_from_url(ws_url: &Url) -> String {
    let mut label = format!("{}://{}", ws_url.scheme(), ws_url.host_str().unwrap_or("session"));

    if let Some(port) = ws_url.port() {
        label.push(':');
        label.push_str(&port.to_string());
    }

    let path = ws_url.path();
    if !path.is_empty() && path != "/" {
        label.push_str(path);
    } else {
        label.push('/');
    }

    label
}

fn session_label_from_status(status: Option<SessionStatus>, fallback: &Url) -> String {
    if let Some(status) = status {
        let title = status.title.trim();
        if title.is_empty() {
            format!("[{}:{}]", status.name, status.port)
        } else {
            format!("[{}:{}] {}", status.name, status.port, title)
        }
    } else {
        session_label_from_url(fallback)
    }
}

fn fetch_session_status(agent: &Agent, status_url: &Url) -> Option<SessionStatus> {
    let response = agent.get(&status_url.to_string()).call().ok()?;
    let body = response.into_string().ok()?;
    serde_json::from_str(&body).ok()
}

fn map_key_to_bytes(key: KeyEvent) -> Option<Vec<u8>> {
    if matches!(key.kind, KeyEventKind::Release) {
        return None;
    }

    if key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL) {
        return None;
    }

    let sequence = match (key.code, key.modifiers) {
        (KeyCode::Char('c' | 'C'), mods) if mods.contains(KeyModifiers::CONTROL) => vec![0x03],
        (KeyCode::Char('d' | 'D'), mods) if mods.contains(KeyModifiers::CONTROL) => vec![0x04],
        (KeyCode::Char(c), mods) if mods.contains(KeyModifiers::CONTROL) => {
            let upper = (c as u8).to_ascii_uppercase();
            if (b'A'..=b'Z').contains(&upper) {
                vec![upper - b'A' + 1]
            } else {
                return None;
            }
        }
        (KeyCode::Enter, _) => b"\r".to_vec(),
        (KeyCode::Tab, _) => b"\t".to_vec(),
        (KeyCode::Backspace, _) => b"\x7f".to_vec(),
        (KeyCode::Delete, _) => b"\x1b[3~".to_vec(),
        (KeyCode::Insert, _) => b"\x1b[2~".to_vec(),
        (KeyCode::Esc, _) => b"\x1b".to_vec(),
        (KeyCode::Up, _) => b"\x1b[A".to_vec(),
        (KeyCode::Down, _) => b"\x1b[B".to_vec(),
        (KeyCode::Right, _) => b"\x1b[C".to_vec(),
        (KeyCode::Left, _) => b"\x1b[D".to_vec(),
        (KeyCode::Home, _) => b"\x1b[H".to_vec(),
        (KeyCode::End, _) => b"\x1b[F".to_vec(),
        (KeyCode::PageUp, _) => b"\x1b[5~".to_vec(),
        (KeyCode::PageDown, _) => b"\x1b[6~".to_vec(),
        (KeyCode::F(1), _) => b"\x1bOP".to_vec(),
        (KeyCode::F(2), _) => b"\x1bOQ".to_vec(),
        (KeyCode::F(3), _) => b"\x1bOR".to_vec(),
        (KeyCode::F(4), _) => b"\x1bOS".to_vec(),
        (KeyCode::F(5), _) => b"\x1b[15~".to_vec(),
        (KeyCode::F(6), _) => b"\x1b[17~".to_vec(),
        (KeyCode::F(7), _) => b"\x1b[18~".to_vec(),
        (KeyCode::F(8), _) => b"\x1b[19~".to_vec(),
        (KeyCode::F(9), _) => b"\x1b[20~".to_vec(),
        (KeyCode::F(10), _) => b"\x1b[21~".to_vec(),
        (KeyCode::F(11), _) => b"\x1b[23~".to_vec(),
        (KeyCode::F(12), _) => b"\x1b[24~".to_vec(),
        (KeyCode::Char(c), _) => c.to_string().into_bytes(),
        _ => return None,
    };

    if key.modifiers.contains(KeyModifiers::ALT) {
        let mut out = vec![0x1b];
        out.extend_from_slice(&sequence);
        Some(out)
    } else {
        Some(sequence)
    }
}

fn map_mouse_to_bytes(
    engine: &mut dyn TerminalEngine,
    mouse_kind: MouseEventKind,
    col: u16,
    row: u16,
    modifiers: KeyModifiers,
) -> Option<Vec<u8>> {
    if engine.mouse_mode() == par_term_emu_core_rust::mouse::MouseMode::Off {
        return None;
    }

    let modifiers = modifiers.bits();
    let (button, pressed) = match mouse_kind {
        MouseEventKind::Down(button) => (
            match button {
                MouseButton::Left => 0,
                MouseButton::Middle => 1,
                MouseButton::Right => 2,
            },
            true,
        ),
        MouseEventKind::Up(button) => (
            match button {
                MouseButton::Left => 0,
                MouseButton::Middle => 1,
                MouseButton::Right => 2,
            },
            false,
        ),
        MouseEventKind::Drag(button) => (
            match button {
                MouseButton::Left => 0,
                MouseButton::Middle => 1,
                MouseButton::Right => 2,
            },
            true,
        ),
        MouseEventKind::ScrollUp => (64, true),
        MouseEventKind::ScrollDown => (65, true),
        _ => return None,
    };

    let event = par_term_emu_core_rust::mouse::MouseEvent::new(
        button,
        col as usize,
        row as usize,
        pressed,
        modifiers,
    );
    Some(engine.report_mouse(event))
}

async fn run() -> DynResult<()> {
    let mut guard = TerminalGuard::enter()?;

    {
        let mut stdout = io::stdout();
        write!(stdout, "\x1b[?1007l")?;
        stdout.flush()?;
    }

    let ws_url = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "ws://127.0.0.1:20000/ws".to_string());
    let parsed_ws_url = Url::parse(&ws_url)?;

    let http_base = ws_to_http_base(&parsed_ws_url);
    let mut status_url = http_base.clone();
    status_url.set_path("/status");
    let mut clear_url = http_base.clone();
    clear_url.set_path("/clear");

    let mut resize_url = http_base.clone();
    resize_url.set_path("/resize");

    let http_agent = Arc::new(Agent::new());
    let session_status = fetch_session_status(&http_agent, &status_url);
    let session_label = session_label_from_status(session_status, &parsed_ws_url);

    let (cols, rows) = terminal::size().unwrap_or((80, 24));
    let content_rows = content_rows_for_terminal(rows);
    request_resize(Arc::clone(&http_agent), resize_url.to_string(), content_rows, cols).await?;

    clear_local_screen()?;

    let mut engine = ParTermEngine::new(cols as usize, content_rows as usize);
    let mut renderer = CrosstermTerminalRenderer::new();

    let connection = match SessionConnection::connect(&parsed_ws_url).await {
        Ok(connection) => connection,
        Err(err) => {
            guard.restore();
            eprintln!("WebSocket connect failed: {err}");
            return Err(err.into());
        }
    };

    let SessionConnection {
        input_tx,
        mut output_rx,
        mut status_rx,
        disconnect_reason,
        reader_handle,
        writer_handle,
    } = connection;

    let (tx_term, mut rx_term) = mpsc::unbounded_channel::<UiEvent>();

    let tick_tx = tx_term.clone();

    let _input_handle = thread::spawn(move || {
        while let Ok(evt) = event::read() {
            if tx_term.send(UiEvent::Input(evt)).is_err() {
                break;
            }
        }
    });

    let _tick_handle = thread::spawn(move || loop {
        thread::sleep(Duration::from_secs(1));
        if tick_tx.send(UiEvent::Tick).is_err() {
            break;
        }
    });

    let mut should_quit = false;
    let mut detach_notice: Option<String> = None;

    renderer.render(&mut engine, *status_rx.borrow(), &session_label)?;

    while !should_quit {
        tokio::select! {
            maybe_data = output_rx.recv() => {
                match maybe_data {
                    Some(data) => {
                        engine.process_output(&data);
                        while let Ok(extra) = output_rx.try_recv() {
                            engine.process_output(&extra);
                        }

                        renderer.render(&mut engine, *status_rx.borrow(), &session_label)?;

                        let responses = engine.drain_responses();
                        if !responses.is_empty() {
                            let _ = input_tx.send(responses);
                        }
                    }
                    None => break,
                }
            }
            maybe_evt = rx_term.recv() => {
                match maybe_evt {
                    Some(UiEvent::Input(Event::Key(key))) => {
                        if key.kind == KeyEventKind::Release {
                            continue;
                        }

                        if key.code == KeyCode::Char('q')
                            && key.modifiers.contains(KeyModifiers::CONTROL)
                        {
                            detach_notice = Some(format!(
                                "Detached from {session_label}. Reconnect with `silc-tui {ws_url}`."
                            ));
                            should_quit = true;
                            continue;
                        }

                        let is_clear_combo = key.modifiers.contains(KeyModifiers::CONTROL)
                            && matches!(key.code, KeyCode::Char('l') | KeyCode::Char('L'));
                        if is_clear_combo {
                            tokio::spawn(request_clear(
                                Arc::clone(&http_agent),
                                clear_url.to_string(),
                            ));
                            engine.reset();
                            renderer.reset();
                            let _ = clear_local_screen();
                            renderer.render(&mut engine, *status_rx.borrow(), &session_label)?;
                            continue;
                        }

                        if let Some(sequence) = map_key_to_bytes(key) {
                            let _ = input_tx.send(sequence);
                        }
                    }
                    Some(UiEvent::Input(Event::Paste(text))) => {
                        if !text.is_empty() {
                            engine.paste(&text);
                            let responses = engine.drain_responses();
                            if !responses.is_empty() {
                                let _ = input_tx.send(responses);
                            }
                        }
                    }
                    Some(UiEvent::Input(Event::Resize(cols, rows))) => {
                        let content_rows = content_rows_for_terminal(rows);
                        let _ = request_resize(
                            Arc::clone(&http_agent),
                            resize_url.to_string(),
                            content_rows,
                            cols,
                        )
                        .await;

                        engine.resize(cols as usize, content_rows as usize);
                        renderer.reset();
                        renderer.render(&mut engine, *status_rx.borrow(), &session_label)?;
                    }
                    Some(UiEvent::Input(Event::Mouse(mouse))) => {
                        if mouse.row as usize >= engine.rows() {
                            continue;
                        }

                        let kind = mouse.kind;
                        let raw = match kind {
                            MouseEventKind::Down(_)
                            | MouseEventKind::Up(_)
                            | MouseEventKind::Drag(_)
                            | MouseEventKind::ScrollUp
                            | MouseEventKind::ScrollDown => {
                                map_mouse_to_bytes(&mut engine, kind, mouse.column, mouse.row, mouse.modifiers)
                            }
                            _ => None,
                        };

                        if let Some(sequence) = raw {
                            let _ = input_tx.send(sequence);
                        }
                    }
                    Some(UiEvent::Input(Event::FocusGained)) => {
                        let focus = engine.report_focus_in();
                        if !focus.is_empty() {
                            let _ = input_tx.send(focus);
                        }
                    }
                    Some(UiEvent::Input(Event::FocusLost)) => {
                        let focus = engine.report_focus_out();
                        if !focus.is_empty() {
                            let _ = input_tx.send(focus);
                        }
                    }
                    Some(UiEvent::Tick) => {
                        renderer.render(&mut engine, *status_rx.borrow(), &session_label)?;
                    }
                    None => break,
                }
            }
            changed = status_rx.changed() => {
                if changed.is_err() || *status_rx.borrow() == ConnectionState::Disconnected {
                    break;
                }
            }
        }
    }

    guard.restore();

    reader_handle.abort();
    writer_handle.abort();

    if let Some(message) = detach_notice {
        eprintln!("{message}");
    } else if *status_rx.borrow() == ConnectionState::Disconnected {
        let reason = disconnect_reason
            .lock()
            .ok()
            .and_then(|guard| guard.clone())
            .unwrap_or_else(|| "Disconnected: connection closed".to_string());
        eprintln!("{reason}");
    }

    Ok(())
}

#[tokio::main]
async fn main() -> DynResult<()> {
    run().await
}
