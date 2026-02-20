# Glossary

This document defines terms used throughout SILC documentation. Link to this instead of re-defining terms.

---

## Daemon

The background process that manages sessions. Listens on port 19999 for management API requests. Creates and destroys sessions on demand. See [arch_daemon.md](arch_daemon.md).

---

## Session

An independent shell with its own PTY (pseudo-terminal). Each session:
- Has a unique port (20000+)
- Has a unique session ID (8-char UUID)
- Maintains its own output buffer
- Can be accessed via CLI, HTTP API, or WebSocket

See [arch_core.md](arch_core.md).

---

## PTY (Pseudo-Terminal)

A virtual terminal that allows programs to interact as if connected to a real terminal. SILC uses:
- `pty` module on Unix (Linux, macOS)
- `pywinpty` / `winpty` on Windows

See [arch_core.md](arch_core.md#pty-implementation).

---

## Sentinel Marker

Special markers used to delimit command output:

```
__SILC_BEGIN_<token>__
<command output>
__SILC_END_<token>:<exit_code>
```

Used for reliable output capture across different shells.

---

## Ring Buffer

A fixed-size buffer that overwrites oldest data when full. Used for terminal output storage. See `RawByteBuffer` in [arch_core.md](arch_core.md#output-buffer).

---

## API Token

A secret string used to authenticate API requests. Required for non-localhost connections. Generated automatically or specified via `--token` flag.

---

## Localhost Bypass

Connections from localhost (127.0.0.1, ::1) don't require API token validation. Convenience for local development.

---

## TUI (Terminal User Interface)

An interactive terminal interface for viewing and interacting with sessions. SILC provides:
- Native TUI (Rust binary, recommended)
- Textual TUI (Python, deprecated)

See [arch_tui.md](arch_tui.md).

---

## WebSocket

A bidirectional communication protocol used for real-time terminal output streaming. Connect at `/ws` endpoint.

---

## SSE (Server-Sent Events)

A unidirectional HTTP-based protocol for streaming server updates. Available at `/stream` endpoint.

---

## Render Mode

Streaming mode that overwrites file with current terminal state (like a TUI snapshot).

---

## Append Mode

Streaming mode that appends new lines to file with deduplication.

---

## Shell Info

Data structure containing shell configuration:
- `type`: Shell type (bash, zsh, sh, pwsh, cmd)
- `path`: Shell executable path
- `prompt_pattern`: Regex to detect shell prompt

---

## Helper Function

A shell function injected into the session for command execution:

```bash
__silc_exec() { 
    printf "__SILC_BEGIN_$2__\n"
    eval "$1"
    printf "__SILC_END_$2__:%d\n" $?
}
```

---

## Session Registry

In-memory tracking of active sessions. Maps port → session metadata.

---

## PID File

A file containing the daemon process ID. Used to detect if daemon is already running. Located at `~/.silc/daemon.pid`.

---

## Garbage Collection

Background process that closes idle sessions (default: 30 minutes idle).

---

## Hard Exit

Forced process termination using `os._exit()`. Used as watchdog when graceful shutdown fails.
