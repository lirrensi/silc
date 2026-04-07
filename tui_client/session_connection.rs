// FILE: tui_client/session_connection.rs
// PURPOSE: Own websocket session transport, frame decoding, and byte-forwarding to the daemon.
// OWNS: WebSocket framing, transport lifecycle, and input/output channels.
// EXPORTS: ConnectionState, SessionConnection, request_clear, request_resize.
// DOCS: agent_chat/plan_rust_tui_par_term_remake_2026-04-07.md

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::{
    io,
    sync::{Arc, Mutex},
};
use tokio::{
    sync::{mpsc, watch},
    task,
    task::JoinHandle,
};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use ureq::Agent;
use url::Url;

pub type DynError = Box<dyn std::error::Error>;
pub type DynResult<T> = Result<T, DynError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionState {
    Connected,
    Disconnected,
}

pub struct SessionConnection {
    pub input_tx: mpsc::UnboundedSender<Vec<u8>>,
    pub output_rx: mpsc::UnboundedReceiver<Vec<u8>>,
    pub status_rx: watch::Receiver<ConnectionState>,
    pub disconnect_reason: Arc<Mutex<Option<String>>>,
    pub reader_handle: JoinHandle<()>,
    pub writer_handle: JoinHandle<()>,
}

impl SessionConnection {
    pub async fn connect(ws_url: &Url) -> DynResult<Self> {
        let (ws_stream, _) = connect_async(ws_url.as_str()).await?;

        let (status_tx, status_rx) = watch::channel(ConnectionState::Connected);
        let disconnect_reason = Arc::new(Mutex::new(None::<String>));

        let (mut ws_write, mut ws_read) = ws_stream.split();
        ws_write
            .send(Message::Binary(
                encode_ws_frame(&json!({"type": "load_history"}), &[])?.into(),
            ))
            .await?;

        let (input_tx, mut input_rx) = mpsc::unbounded_channel::<Vec<u8>>();
        let (output_tx, output_rx) = mpsc::unbounded_channel::<Vec<u8>>();

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
                                    let _ = output_tx.send(payload);
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
                                        format!("Disconnected: websocket closed (code {code}): {reason}")
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

        let writer_handle = {
            let status_tx = status_tx.clone();
            let disconnect_reason = Arc::clone(&disconnect_reason);
            tokio::spawn(async move {
                while let Some(chunk) = input_rx.recv().await {
                    if chunk.is_empty() {
                        continue;
                    }

                    let frame =
                        match encode_ws_frame(&json!({"type": "input", "nonewline": true}), &chunk)
                        {
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

        Ok(Self {
            input_tx,
            output_rx,
            status_rx,
            disconnect_reason,
            reader_handle,
            writer_handle,
        })
    }
}

pub async fn request_clear(agent: Arc<Agent>, clear_url: String) {
    let _ = task::spawn_blocking(move || agent.post(&clear_url).call()).await;
}

pub async fn request_resize(
    agent: Arc<Agent>,
    resize_url: String,
    rows: u16,
    cols: u16,
) -> DynResult<()> {
    task::spawn_blocking(move || {
        let rows_s = rows.to_string();
        let cols_s = cols.to_string();
        agent
            .post(&resize_url)
            .query("rows", &rows_s)
            .query("cols", &cols_s)
            .call()
    })
    .await??;

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
        return Err(
            io::Error::new(io::ErrorKind::InvalidData, "frame header must be object").into(),
        );
    }

    Ok((header, data[4 + header_len..].to_vec()))
}

fn set_disconnect_reason(slot: &Arc<Mutex<Option<String>>>, reason: String) {
    if let Ok(mut guard) = slot.lock() {
        if guard.is_none() {
            *guard = Some(reason);
        }
    }
}
