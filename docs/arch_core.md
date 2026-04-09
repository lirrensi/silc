# Architecture: Core

This document describes `silc/core/`.

## Overview

The core layer owns the PTY-backed session runtime:

- shell process creation and PTY I/O
- shell startup that preserves native profiles/init files
- output buffering and rendering
- command execution with sentinel capture
- title/cwd extraction from PTY output
- live session status and lifecycle methods

## Scope Boundary

Owns:

- PTY lifecycle and I/O
- session runtime state
- output buffering, cleaning, and snapshots
- prompt/title/cwd tracking

Does not own:

- daemon record management (`silc/daemon/`)
- session HTTP/WebSocket routing or port adapters (`silc/api/server.py`)
- CLI parsing (`silc/__main__.py`)

## Key Modules

| Module | Role |
|---|---|
| `silc/core/session.py` | `SilcSession` orchestration |
| `silc/core/pty_manager.py` | PTY abstraction/factory |
| `silc/core/raw_buffer.py` | Raw PTY ring buffer |
| `silc/core/cleaner.py` | Output cleaning |
| `silc/core/osc.py` | OSC title/CWD parsing |

## `SilcSession`

Important fields:

```python
port: int
name: str
shell_info: ShellInfo
session_id: str
api_token: str | None
cwd: str | None
command: dict[str, str] | None
title: str
title_updated_at: datetime
buffer: RawByteBuffer
created_at: datetime
last_access: datetime
last_output: datetime
screen_columns: int
screen_rows: int
tui_active: bool
run_lock: asyncio.Lock
input_lock: asyncio.Lock
current_run_cmd: str | None
```

## Lifecycle

- `__init__` creates the PTY, buffer, listeners, and default terminal geometry.
- `start()` creates the read loop and a background GC task after a short startup grace period.
- The GC task only rotates logs; sessions do **not** auto-expire.
- `close()` cancels background tasks and kills the PTY.
- `force_kill()` is a more aggressive close path with shorter waits.

## Read Loop

- The read loop pulls bytes from the PTY and appends them to the ring buffer.
- OSC title, hidden-cwd, and hidden-command sequences are parsed from the raw stream.
- Live title/cwd listeners are notified when those values change.
- Live command listeners are notified when the last entered command changes.
- Status metadata caches the latest visible line and a heuristic `waiting_for_input` flag.
- Session output is written to the per-session log file.

## Output Retrieval

- `get_output(lines, raw=False)` returns either raw buffered output or a rendered terminal snapshot.
- `get_rendered_output()` uses `par_term_emu_core_rust` when available.
- Fallback rendering uses the cleaner and strips sentinel markers.
- `get_snapshot_bytes()` caches raw bytes for preview rendering.

## Command Execution

`run_command()`:

1. Rejects concurrent runs with a `busy` response.
2. Wraps the requested command in a shell-specific helper invocation.
3. Waits for begin/end sentinels and captures exit code.
4. Caps collected output at 5 MB; overflow sends Ctrl+C and returns an error.
5. Returns `completed`, `timeout`, or `error` with cleaned output.

## Input and Terminal Control

- `write_input()` writes raw bytes to the PTY.
- `interrupt()` sends Ctrl+C.
- `send_sigterm()` and `send_sigkill()` delegate to the PTY process-group helpers.
- `clear_screen()` clears SILC's buffered terminal state without injecting control sequences into the PTY.
- `resize()` updates PTY and renderer geometry.

## Status Model

`get_status()` returns:

- `session_id`
- `port`
- `name`
- `title`
- `cwd`
- `command`
- `title_updated_at`
- `alive`
- `idle_seconds`
- `waiting_for_input`
- `last_line`
- `run_locked`

`idle_seconds` is informational; it does not close the session.

## Listeners

The session supports live listeners for:

- title changes
- cwd changes
- command changes
- raw output chunks

The daemon uses these listeners to persist updates back into the registry.

## PTY Creation

PTY selection is delegated to `create_pty()` in `pty_manager.py` based on platform.
Shell launch specs layer SILC helpers on top of the shell's normal startup files.
Launch cwd is normalized before spawn; invalid or unusable cwd values fall back to the user's home directory or the shell default so launch/restart stays resilient.

## Error Handling

- PTY creation failure aborts session creation.
- Read-loop exceptions end the session runtime.
- Buffer overflow interrupts the foreground command.
- Write/read operations are best-effort and avoid hanging the daemon.
