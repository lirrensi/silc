# commands_and_api.md

## SILC CLI Commands

| Command | Options | Description |
|---------|---------|-------------|
| `silc start [--port <n>] [--global] [--no-detach]` | `--port` – specific port; default finds a free one.<br>`--global` – bind to `0.0.0.0` (exposes session to all interfaces, *dangerous*).<br>`--no-detach` – run daemon in the foreground. | Starts the SILC daemon if not running and creates a new session. The session port and ID are printed. |
| `silc <port> out [<lines>]` | `lines` – number of lines to fetch (default 100). | Fetch the latest terminal output from the session. |
| `silc <port> in <text…>` | `text` – raw input to send to the shell. | Sends the given string (with platform newline) to the session. |
| `silc <port> run <command…>` | `command` – shell command to execute. | Executes the command in the session, waits for sentinel markers, returns `output`, `exit_code`, and `status`. |
| `silc <port> resize <rows> <cols>` | `rows`, `cols` – terminal dimensions. | Resizes the PTY and renderer. |
| `silc <port> interrupt` | | Sends Ctrl‑C to the session. |
| `silc <port> clear` | | Clears the internal output buffer. |
| `silc <port> close` | | Gracefully closes the session. |
| `silc <port> kill` | | Forces the session to terminate immediately. |
| `silc <port> logs [--tail N]` | `--tail` – number of log lines to show (default 100). | Shows the per‑session log. |
| `silc list` | | Lists all active sessions with port, ID, shell, idle time, and alive status. |
| `silc shutdown` | | Gracefully shuts down the daemon and all sessions. |
| `silc killall` | | Force‑kills all sessions and the daemon. |
| `silc open` | | Deprecated: opens the Textual TUI for the most recently started session. |
| `silc <port> tui` | | Launch the native SILC TUI guest for the session; downloads the prebuilt release binary if needed. |

### Usage Examples

```bash
# Start a new session on a free port
silc start

# Start a session on a specific port
silc start --port 20000

# Run a command in session 20000
silc 20000 run "ls -la"

# Get the last 50 lines of output
silc 20000 out 50

# Resize the terminal
silc 20000 resize 40 120

# Open the Textual TUI (deprecated)
silc open
```

### Native TUI Installer

When you run `silc <port> tui` the CLI looks for a locally built binary in `tui_client/dist` and, if absent, lazily downloads the latest GitHub release into `platformdirs.user_cache_dir("silc") / "bin"` (you can force a different cache directory with `SILC_TUI_BIN_DIR`). The download endpoint defaults to `https://api.github.com/repos/yourorg/silc-tui/releases/latest`; replace `yourorg/silc-tui` with the real repository path once the Rust client publishes releases, or point at a fork via `SILC_TUI_RELEASE_REPO` or a custom API URL with `SILC_TUI_RELEASE_API`. If the release asset for your platform is missing the command reports the failure and falls back to the local `tui_client` build instructions described in `docs/rust_pack_solution.md`.
The installer already understands Linux, Windows, and macOS (`darwin`) builds so future releases can ship cross-platform assets.

---

## REST API

The API is exposed by the FastAPI server created in `silc/api/server.py`. All endpoints (except `/web`) require a valid API token unless the client is connecting from localhost. The token can be obtained by calling `/token` or by inspecting the `api_token` attribute of a session.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Return the session status (alive, idle_time, etc). |
| `GET` | `/out?lines=N` | Return the last N lines of terminal output. |
| `GET` | `/raw?lines=N` | Return raw output (no cleaning). |
| `GET` | `/logs?tail=N` | Return the last N lines of the session log. |
| `GET` | `/stream` | Server‑sent events stream of terminal output. |
| `POST` | `/in` | Send raw input to the session. Body is the text to send. |
| `POST` | `/run` | Execute a shell command. Body can be plain text or JSON `{ "command": "…", "timeout": 60 }`. |
| `POST` | `/interrupt` | Send Ctrl‑C to the session. |
| `POST` | `/clear` | Clear the internal output buffer. |
| `POST` | `/resize` | Resize PTY. Body: `{ "rows": 40, "cols": 120 }`. |
| `POST` | `/close` | Gracefully close the session. |
| `POST` | `/kill` | Force‑kill the session. |
| `GET` | `/token` | Return the current session token (if any). |
| `GET` | `/web` | Serve the static web UI. |

---

## WebSocket API

A WebSocket connection can be established at `/ws`. The connection requires a token query parameter if the server is not on localhost. Example:

```text
ws://localhost:8000/ws?token=YOUR_TOKEN
```

Once connected, the server sends JSON messages with the shape:

```json
{ "event": "update", "data": "… terminal output …" }
```

Clients may send JSON messages to send input to the terminal:

```json
{ "event": "type", "text": "ls -la", "nonewline": false }
```

If `nonewline` is `true`, the string is sent as‑is; otherwise a platform‑specific newline is appended.

The connection stays open until the client disconnects or the session ends. On disconnect, the server resets `session.tui_active`.

---

# End of file
