use crossterm::{
    cursor,
    event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers},
    execute,
    terminal::{self, Clear, ClearType},
};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::{
    io::{self, Write},
    sync::Arc,
    time::Duration,
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

#[derive(Serialize, Debug)]
struct WsTypeMessage {
    event: &'static str,
    text: String,
    nonewline: bool,
}

#[derive(Deserialize, Debug)]
struct WsUpdateMessage {
    event: String,
    #[serde(default)]
    data: String,
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

async fn fetch_initial_raw(agent: Arc<Agent>, raw_url: String) -> Option<String> {
    task::spawn_blocking(move || {
        let response = agent.get(&raw_url).call().ok()?;
        let body = response.into_string().ok()?;
        let json: serde_json::Value = serde_json::from_str(&body).ok()?;
        json.get("output")
            .and_then(|v| v.as_str())
            .map(str::to_string)
    })
    .await
    .ok()
    .flatten()
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
    let mut raw_url = http_base.clone();
    raw_url.set_path("/raw");
    raw_url.set_query(Some("lines=200"));

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

    // Best-effort: show some existing scrollback so the UI isn't empty.
    if let Some(initial) = fetch_initial_raw(Arc::clone(&http_agent), raw_url.to_string()).await {
        if !initial.is_empty() {
            let mut stdout = io::stdout();
            write!(stdout, "{}", initial)?;
            stdout.flush()?;
        }
    }

    let (status_tx, status_rx) = watch::channel(ConnectionState::Connected);

    let (mut ws_write, mut ws_read) = ws_stream.split();

    let (tx_input, mut rx_input) = mpsc::unbounded_channel::<String>();
    let (tx_output, mut rx_output) = mpsc::unbounded_channel::<Vec<u8>>();

    // WebSocket reader: terminal output
    let reader_handle = {
        let status_tx = status_tx.clone();
        tokio::spawn(async move {
            while let Some(next) = ws_read.next().await {
                match next {
                    Ok(Message::Text(text)) => {
                        let payload = text.as_str();
                        if let Ok(msg) = serde_json::from_str::<WsUpdateMessage>(payload) {
                            if msg.event == "update" && !msg.data.is_empty() {
                                let _ = tx_output.send(msg.data.into_bytes());
                            }
                        } else {
                            let _ = tx_output.send(payload.as_bytes().to_vec());
                        }
                    }
                    Ok(Message::Binary(data)) => {
                        let _ = tx_output.send(data.to_vec());
                    }
                    Ok(Message::Close(_)) => {
                        break;
                    }
                    Ok(_) => {}
                    Err(_) => {
                        break;
                    }
                }
            }
            let _ = status_tx.send(ConnectionState::Disconnected);
        })
    };

    // WebSocket writer: keyboard input
    let writer_handle = {
        let status_tx = status_tx.clone();
        tokio::spawn(async move {
            while let Some(chunk) = rx_input.recv().await {
                if chunk.is_empty() {
                    continue;
                }
                let msg = WsTypeMessage {
                    event: "type",
                    text: chunk,
                    nonewline: true,
                };

                let json = match serde_json::to_string(&msg) {
                    Ok(json) => json,
                    Err(_) => continue,
                };

                if ws_write.send(Message::Text(json.into())).await.is_err() {
                    let _ = status_tx.send(ConnectionState::Disconnected);
                    break;
                }
            }
        })
    };

    let mut should_quit = false;

    while !should_quit {
        // Render any new remote output.
        while let Ok(data) = rx_output.try_recv() {
            let mut stdout = io::stdout();
            stdout.write_all(&data)?;
            stdout.flush()?;
        }

        if *status_rx.borrow() == ConnectionState::Disconnected {
            break;
        }

        // Keyboard + resize + paste handling.
        if event::poll(Duration::from_millis(25))? {
            match event::read()? {
                Event::Key(key) => {
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
                Event::Paste(text) => {
                    if !text.is_empty() {
                        let _ = tx_input.send(text);
                    }
                }
                Event::Resize(cols, rows) => {
                    tokio::spawn(request_resize(
                        Arc::clone(&http_agent),
                        resize_url.to_string(),
                        rows,
                        cols,
                    ));
                }
                _ => {}
            }
        }
    }

    reader_handle.abort();
    writer_handle.abort();

    guard.restore();

    if *status_rx.borrow() == ConnectionState::Disconnected {
        eprintln!("Disconnected");
    }

    Ok(())
}
