// FILE: tui_client/main.rs
// PURPOSE: Run the native SILC TUI client over framed binary websocket transport.
// OWNS: Native websocket framing, keyboard input encoding, and terminal output rendering.
// EXPORTS: main - launch the standalone TUI client binary.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

use crossterm::{
    cursor,
    event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers},
    execute,
    terminal::{self, Clear, ClearType},
};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::{
    io::{self, Write},
    sync::{Arc, Mutex},
    thread,
};
use tokio::sync::{mpsc, watch};
use tokio::task;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use ureq::Agent;
use url::Url;

type DynError = Box<dyn std::error::Error>;
type DynResult<T> = Result<T, DynError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ConnectionState {
    Connected,
    Disconnected,
}

struct TerminalGuard {
    restored: bool,
}

impl TerminalGuard {
    fn enter() -> DynResult<Self> {
        // Raw mode is required so we can capture keys (including Enter/Arrows/Ctrl).
        //
        // NOTE: We intentionally do NOT enter the alternate screen buffer, because many
        // terminals map mouse wheel scrolling to Up/Down keys while in the alt buffer.
        // For SILC this is undesirable: it triggers shell history navigation instead of
        // local scrollback.
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

    // Strip websocket path; endpoints are absolute (e.g. /ws, /clear).
    http.set_path("/");
    http.set_query(None);
    http.set_fragment(None);
    http
}

fn map_key_to_sequence(key: KeyEvent) -> Option<String> {
    if matches!(key.kind, KeyEventKind::Release) {
        return None;
    }

    // Ctrl+Q is reserved for quitting locally.
    if key.code == KeyCode::Char('q') && key.modifiers.contains(KeyModifiers::CONTROL) {
        return None;
    }

    // Ctrl+<letter> handling
    let sequence = match (key.code, key.modifiers) {
        (KeyCode::Char('c' | 'C'), mods) if mods.contains(KeyModifiers::CONTROL) => "\x03".to_string(),
        (KeyCode::Char('d' | 'D'), mods) if mods.contains(KeyModifiers::CONTROL) => "\x04".to_string(),
        (KeyCode::Char(c), mods) if mods.contains(KeyModifiers::CONTROL) => {
            let upper = (c as u8).to_ascii_uppercase();
            if (b'A'..=b'Z').contains(&upper) {
                String::from_utf8(vec![upper - b'A' + 1]).ok()?
            } else {
                return None;
            }
        }

        // Common terminal keys
        (KeyCode::Enter, _) => "\r".to_string(),
        (KeyCode::Tab, _) => "\t".to_string(),
        (KeyCode::Backspace, _) => "\x7f".to_string(),
        (KeyCode::Delete, _) => "\x1b[3~".to_string(),
        (KeyCode::Insert, _) => "\x1b[2~".to_string(),
        (KeyCode::Esc, _) => "\x1b".to_string(),

        (KeyCode::Up, _) => "\x1b[A".to_string(),
        (KeyCode::Down, _) => "\x1b[B".to_string(),
        (KeyCode::Right, _) => "\x1b[C".to_string(),
        (KeyCode::Left, _) => "\x1b[D".to_string(),
        (KeyCode::Home, _) => "\x1b[H".to_string(),
        (KeyCode::End, _) => "\x1b[F".to_string(),
        (KeyCode::PageUp, _) => "\x1b[5~".to_string(),
        (KeyCode::PageDown, _) => "\x1b[6~".to_string(),

        // Function keys (xterm-ish)
        (KeyCode::F(1), _) => "\x1bOP".to_string(),
        (KeyCode::F(2), _) => "\x1bOQ".to_string(),
        (KeyCode::F(3), _) => "\x1bOR".to_string(),
        (KeyCode::F(4), _) => "\x1bOS".to_string(),
        (KeyCode::F(5), _) => "\x1b[15~".to_string(),
        (KeyCode::F(6), _) => "\x1b[17~".to_string(),
        (KeyCode::F(7), _) => "\x1b[18~".to_string(),
        (KeyCode::F(8), _) => "\x1b[19~".to_string(),
        (KeyCode::F(9), _) => "\x1b[20~".to_string(),
        (KeyCode::F(10), _) => "\x1b[21~".to_string(),
        (KeyCode::F(11), _) => "\x1b[23~".to_string(),
        (KeyCode::F(12), _) => "\x1b[24~".to_string(),

        // Printable characters
        (KeyCode::Char(c), _) => c.to_string(),

        _ => return None,
    };

    // Alt modifier usually prefixes ESC.
    if key.modifiers.contains(KeyModifiers::ALT) {
        Some(format!("\x1b{}", sequence))
    } else {
        Some(sequence)
    }
}

fn clear_local_screen() -> DynResult<()> {
    let mut stdout = io::stdout();
    execute!(stdout, Clear(ClearType::All), cursor::MoveTo(0, 0))?;
    stdout.flush()?;
    Ok(())
}

fn encode_ws_frame(header: &Value, payload: &[u8]) -> DynResult<Vec<u8>> {
    let header_bytes = serde_json::to_vec(header)?;
    let header_len: u32 = header_bytes
        .len()
        .try_into()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "frame header too large"))?;

    let mut frame = Vec::with_capacity(4 + header_bytes.len() + payload.len());
    frame.extend_from_slice(&header_len.to_be_bytes());
    frame.extend_from_slice(&header_bytes);
    frame.extend_from_slice(payload);
    Ok(frame)
}

fn decode_ws_frame(data: &[u8]) -> DynResult<(Value, Vec<u8>)> {
    if data.len() < 4 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "frame too short").into());
    }

    let header_len = u32::from_be_bytes(data[0..4].try_into().unwrap()) as usize;
    if data.len() < 4 + header_len {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "frame truncated").into());
    }

    let header: Value = serde_json::from_slice(&data[4..4 + header_len])?;
    if !header.is_object() {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "frame header must be object").into());
    }

    Ok((header, data[4 + header_len..].to_vec()))
}

fn strip_terminal_query_noise(data: &[u8]) -> Vec<u8> {
    let mut filtered = Vec::with_capacity(data.len());
    let mut i = 0;

    while i < data.len() {
        if i + 3 < data.len() && data[i] == 0x1b && data[i + 1] == b'[' && data[i + 2] == b'?' {
            let mut j = i + 3;
            while j < data.len() && (data[j].is_ascii_digit() || data[j] == b';') {
                j += 1;
            }

            if j < data.len() && data[j] == b'c' {
                i = j + 1;
                continue;
            }
        }

        filtered.push(data[i]);
        i += 1;
    }

    filtered
}

fn set_disconnect_reason(slot: &Arc<Mutex<Option<String>>>, reason: String) {
    if let Ok(mut guard) = slot.lock() {
        if guard.is_none() {
            *guard = Some(reason);
        }
    }
}

async fn request_clear(agent: Arc<Agent>, clear_url: String) {
    let _ = task::spawn_blocking(move || agent.post(&clear_url).call()).await;
}

async fn request_resize(agent: Arc<Agent>, resize_url: String, rows: u16, cols: u16) {
    let _ = task::spawn_blocking(move || {
        let rows_s = rows.to_string();
        let cols_s = cols.to_string();
        agent.post(&resize_url)
            .query("rows", &rows_s)
            .query("cols", &cols_s)
            .call()
    })
    .await;
}

#[tokio::main]
async fn main() -> DynResult<()> {
    let mut guard = TerminalGuard::enter()?;

    // Ask xterm-compatible terminals to *not* translate mouse wheel scrolling into
    // Up/Down key presses ("alternate scroll mode"). This keeps scrollback scrolling
    // local, matching xterm.js behavior.
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
    let mut clear_url = http_base.clone();
    clear_url.set_path("/clear");

    let mut resize_url = http_base.clone();
    resize_url.set_path("/resize");

    let http_agent = Arc::new(Agent::new());

    // Avoid clearing on startup so users can scroll the local terminal history.

    {
        let mut stdout = io::stdout();
        writeln!(
            stdout,
            "SILC TUI client (native)\r\n  WS: {ws_url}\r\n  Ctrl+Q quit · Ctrl+L clear\r\n"
        )?;
        stdout.flush()?;
    }

    // Best-effort: sync PTY size to current terminal.
    if let Ok((cols, rows)) = terminal::size() {
        tokio::spawn(request_resize(
            Arc::clone(&http_agent),
            resize_url.to_string(),
            rows,
            cols,
        ));
    }

    let (ws_stream, _) = match connect_async(&ws_url).await {
        Ok(ok) => ok,
        Err(err) => {
            guard.restore();
            eprintln!("WebSocket connect failed: {err}");
            return Err(err.into());
        }
    };

    let (status_tx, mut status_rx) = watch::channel(ConnectionState::Connected);
    let disconnect_reason = Arc::new(Mutex::new(None::<String>));

    let (mut ws_write, mut ws_read) = ws_stream.split();

    ws_write
        .send(Message::Binary(
            encode_ws_frame(&json!({"type": "load_history"}), &[])?.into(),
        ))
        .await?;

    let (tx_input, mut rx_input) = mpsc::unbounded_channel::<String>();
    let (tx_output, mut rx_output) = mpsc::unbounded_channel::<Vec<u8>>();
    let (tx_term, mut rx_term) = mpsc::unbounded_channel::<Event>();

    let _input_handle = thread::spawn(move || {
        while let Ok(evt) = event::read() {
            if tx_term.send(evt).is_err() {
                break;
            }
        }
    });

    // WebSocket reader: terminal output
    let reader_handle = {
        let status_tx = status_tx.clone();
        let disconnect_reason = Arc::clone(&disconnect_reason);
        tokio::spawn(async move {
            while let Some(next) = ws_read.next().await {
                match next {
                    Ok(Message::Binary(data)) => {
                        let Ok((header, payload)) = decode_ws_frame(&data) else {
                            break;
                        };

                        match header.get("type").and_then(|value| value.as_str()) {
                            Some("output") | Some("history") => {
                                let payload = strip_terminal_query_noise(&payload);
                                if payload.is_empty() {
                                    continue;
                                }
                                let _ = tx_output.send(payload);
                            }
                            Some("title") => {}
                            _ => break,
                        }
                    }
                    Ok(Message::Close(frame)) => {
                        let reason = match frame {
                            Some(frame) => {
                                let code = format!("{:?}", frame.code);
                                let reason = frame.reason.to_string();
                                if reason.is_empty() {
                                    format!("Disconnected: websocket closed (code {code})")
                                } else {
                                    format!(
                                        "Disconnected: websocket closed (code {code}): {reason}"
                                    )
                                }
                            }
                            None => "Disconnected: websocket closed".to_string(),
                        };
                        set_disconnect_reason(&disconnect_reason, reason);
                        break;
                    }
                    Ok(Message::Ping(_)) | Ok(Message::Pong(_)) => {}
                    Ok(Message::Text(text)) => {
                        set_disconnect_reason(
                            &disconnect_reason,
                            format!("Disconnected: unexpected text websocket frame: {text}"),
                        );
                        break;
                    }
                    Ok(_) => {}
                    Err(err) => {
                        set_disconnect_reason(
                            &disconnect_reason,
                            format!("Disconnected: websocket read error: {err}"),
                        );
                        break;
                    }
                }
            }
            set_disconnect_reason(
                &disconnect_reason,
                "Disconnected: connection closed".to_string(),
            );
            let _ = status_tx.send(ConnectionState::Disconnected);
        })
    };

    // WebSocket writer: keyboard input
    let writer_handle = {
        let status_tx = status_tx.clone();
        let disconnect_reason = Arc::clone(&disconnect_reason);
        tokio::spawn(async move {
            while let Some(chunk) = rx_input.recv().await {
                if chunk.is_empty() {
                    continue;
                }
                let frame = match encode_ws_frame(
                    &json!({"type": "input", "nonewline": true}),
                    chunk.as_bytes(),
                ) {
                    Ok(frame) => frame,
                    Err(_) => continue,
                };

                if ws_write.send(Message::Binary(frame.into())).await.is_err() {
                    set_disconnect_reason(
                        &disconnect_reason,
                        "Disconnected: websocket write error".to_string(),
                    );
                    let _ = status_tx.send(ConnectionState::Disconnected);
                    break;
                }
            }
        })
    };

    let mut should_quit = false;

    while !should_quit {
        tokio::select! {
            maybe_data = rx_output.recv() => {
                match maybe_data {
                    Some(data) => {
                        let mut stdout = io::stdout();
                        stdout.write_all(&data)?;
                        stdout.flush()?;

                        while let Ok(extra) = rx_output.try_recv() {
                            stdout.write_all(&extra)?;
                            stdout.flush()?;
                        }
                    }
                    None => break,
                }
            }
            maybe_evt = rx_term.recv() => {
                match maybe_evt {
                    Some(Event::Key(key)) => {
                        if key.kind == KeyEventKind::Release {
                            continue;
                        }

                        if key.code == KeyCode::Char('q')
                            && key.modifiers.contains(KeyModifiers::CONTROL)
                        {
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
                            let _ = clear_local_screen();
                            continue;
                        }

                        if let Some(sequence) = map_key_to_sequence(key) {
                            let _ = tx_input.send(sequence);
                        }
                    }
                    Some(Event::Paste(text)) => {
                        if !text.is_empty() {
                            let _ = tx_input.send(text);
                        }
                    }
                    Some(Event::Resize(cols, rows)) => {
                        tokio::spawn(request_resize(
                            Arc::clone(&http_agent),
                            resize_url.to_string(),
                            rows,
                            cols,
                        ));
                    }
                    Some(_) => {}
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

    reader_handle.abort();
    writer_handle.abort();

    guard.restore();

    if *status_rx.borrow() == ConnectionState::Disconnected {
        let reason = disconnect_reason
            .lock()
            .ok()
            .and_then(|guard| guard.clone())
            .unwrap_or_else(|| "Disconnected: connection closed".to_string());
        eprintln!("{reason}");
    }

    Ok(())
}
