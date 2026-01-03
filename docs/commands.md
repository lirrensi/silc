# commands.md

## SILC CLI Commands

| Command | Options | Description |
|---------|---------|-------------|
| `silc start [--port <n>] [--global] [--no-detach]` | `--port` – specific port; default finds free port.<br>`--global` – bind to `0.0.0.0` (exposes session on all interfaces, *dangerous*).<br>`--no-detach` – run daemon in foreground. | Starts the SILC daemon if not running and creates a new session. The session port and ID are printed. |
| `silc <port> out [<lines>]` | `lines` – number of lines to fetch (default 100). | Fetch the latest terminal output from the session. |
| `silc <port> in <text…>` | `text` – raw input to send to the shell. | Sends the given string (with platform newline) to the session. |
| `silc <port> run <command…>` | `command` – shell command to execute. | Executes the command in the session, waits for sentinel markers, returns `output`, `exit_code`, and `status`. |
| `silc <port> resize <rows> <cols>` | `rows`, `cols` – terminal dimensions. | Resizes the PTY and renderer. |
| `silc <port> interrupt` |  | Sends Ctrl‑C to the session. |
| `silc <port> clear` |  | Clears the internal output buffer. |
| `silc <port> close` |  | Gracefully closes the session. |
| `silc <port> kill` |  | Forces the session to terminate immediately. |
| `silc <port> logs [--tail N]` | `--tail` – number of log lines to show (default 100). | Shows the per‑session log. |
| `silc list` |  | Lists all active sessions with port, ID, shell, idle time, and alive status. |
| `silc shutdown` |  | Gracefully shuts down the daemon and all sessions. |
| `silc killall` |  | Force‑kills all sessions and the daemon. |
| `silc logs [--tail N]` | `--tail` – number of log lines to show (default 100). | Shows the daemon log. |

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

# Open the Textual TUI
silc 20000 open
```

---

