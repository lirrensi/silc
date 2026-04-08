# Glossary

This document defines terms used throughout SILC documentation. Link to this instead of re-defining terms.

---

## Daemon

The background process that owns session records and reconciles live runtime to those records. Listens on port 19999 for management API requests. See [arch_daemon.md](arch_daemon.md).

---

## Session

An independent shell identity owned by a daemon record. Each session:
- Has a unique port (20000+)
- Has a unique session ID (8-char UUID)
- Maintains its own output buffer
- Can be accessed via CLI, HTTP API, or WebSocket

The live PTY is the primary runtime resource for a session, but the session continues to exist conceptually while its record exists, even if runtime is being restarted or reconciled.

See [arch_core.md](arch_core.md).

---

## Session Record

The daemon-owned desired-state entry that defines that a session should exist. Removing the record is the real death of a session.

---

## Session Runtime

The currently realized live resources for a session record, including PTY, adapter, socket, generation, and health state.

---

## Messenger

The replaceable per-port HTTP/WebSocket forwarder attached to a session runtime. Messenger failure does not imply session death.

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

Daemon-owned tracking of desired sessions. The registry is the source of truth for which sessions should exist; live runtime may be recreated to match it.

---

## PID File

A file containing the daemon process ID. Used to detect if daemon is already running. Located at `~/.silc/daemon.pid`.

---

## Garbage Collection

Background daemon work such as reconciliation, log rotation, and bounded cleanup. Session lifetime is controlled by record existence, not idle timeout.

---

## Hard Exit

Forced process termination using `os._exit()`. Used as watchdog when graceful shutdown fails.
