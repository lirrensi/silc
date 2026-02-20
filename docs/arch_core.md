# Architecture: Core (Session, PTY, Buffer, Cleaner)

This document describes the core shell interaction layer. Complete enough to rewrite `silc/core/` from scratch.

---

## Overview

The core layer provides:

- **PTY abstraction** — Cross-platform pseudo-terminal management
- **Session orchestration** — Ties PTY, buffer, and command execution together
- **Output buffering** — Ring buffer for terminal output
- **Output cleaning** — ANSI/control sequence removal

---

## Scope Boundary

**This component owns:**
- PTY creation and lifecycle management
- Session state and command execution
- Output buffering and retrieval
- ANSI/control sequence cleaning
- Shell detection and helper function injection

**This component does NOT own:**
- HTTP/WebSocket API (see [arch_api.md](arch_api.md))
- Daemon management (see [arch_daemon.md](arch_daemon.md))
- CLI parsing (see [arch_cli.md](arch_cli.md))
- Configuration loading (see `silc/config.py`)

**Boundary interfaces:**
- Receives: port number, shell info, API token from daemon
- Exposes: `SilcSession` class with `run_command()`, `get_output()`, `write_input()`, etc.

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `asyncio` | Async I/O | stdlib |
| `psutil` | Process management | any |
| `pty` | Unix PTY (Unix only) | stdlib |
| `pywinpty` / `winpty` | Windows PTY (Windows only) | any |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/config.py` | Configuration values |
| `silc/utils/persistence.py` | Session logging |
| `silc/utils/shell_detect.py` | Shell detection |

---

## Data Models

### `ShellInfo`

```python
@dataclass
class ShellInfo:
    type: str              # "bash", "zsh", "sh", "pwsh", "cmd"
    path: str              # Shell executable path
    prompt_pattern: Pattern[str]  # Regex to detect prompt
```

### `SilcSession`

```python
class SilcSession:
    port: int                    # Session port
    session_id: str              # 8-char UUID
    shell_info: ShellInfo        # Shell configuration
    api_token: str | None        # API token (optional)
    buffer: RawByteBuffer        # Output buffer
    created_at: datetime         # Creation timestamp
    last_access: datetime        # Last access timestamp
    last_output: datetime        # Last output timestamp
    screen_columns: int          # Terminal width (default: 120)
    screen_rows: int             # Terminal height (default: 30)
    tui_active: bool             # TUI connection status
```

### `RawByteBuffer`

```python
class RawByteBuffer:
    maxlen: int                  # Maximum buffer size (default: 65536)
    cursor: int                  # Current read position
```

---

## Component Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                      SilcSession                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    PTY      │  │   Buffer    │  │      Cleaner        │  │
│  │ (PTYBase)   │──│(RawByteBuffer)──│(clean_output)       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│        │                                                    │
│        ▼                                                    │
│  ┌─────────────┐                                           │
│  │   Shell     │                                           │
│  │ (bash/zsh/  │                                           │
│  │  pwsh/cmd)  │                                           │
│  └─────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## PTY Implementation

### `PTYBase` (Abstract)

```python
class PTYBase(ABC):
    pid: int | None

    @abstractmethod
    async def read(self, size: int = 1024) -> bytes: ...

    @abstractmethod
    async def write(self, data: bytes) -> None: ...

    @abstractmethod
    def resize(self, rows: int, cols: int) -> None: ...

    @abstractmethod
    def kill(self) -> None: ...
```

### `UnixPTY`

**Implementation:**
- Uses `pty.openpty()` to create master-slave pair
- Spawns shell via `subprocess.Popen` with `preexec_fn=os.setsid`
- Reads/writes via master file descriptor
- Resizes with `ioctl(TIOCSWINSZ)`
- Kills shell process and closes FD

**Code path:**
```python
import pty, os, subprocess

master_fd, slave_fd = pty.openpty()
process = subprocess.Popen(
    [shell_path],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    preexec_fn=os.setsid,
)
os.close(slave_fd)
```

### `WindowsPTY`

**Implementation:**
- Loads `winpty` or `pywinpty` module
- Spawns shell via `winpty.PtyProcess.spawn()` or `winpty.PTY.spawn()`
- Wraps synchronous read/write in `run_in_executor` for async
- Resizes via `setwinsize(rows, cols)` or `set_size(rows, cols)`
- Kills process tree (parent + children)

**Code path:**
```python
import winpty

process = winpty.PtyProcess.spawn(command, env=env)
# or
pty_handle = winpty.PTY(cols=120, rows=30)
process = pty_handle.spawn(command, env=env)
```

### `StubPTY`

Fallback when platform-specific PTY cannot be loaded. All methods are no-ops.

### Factory: `create_pty()`

```python
def create_pty(shell_cmd: str | None, env: Mapping[str, str]) -> PTYBase:
    if sys.platform == "win32":
        return WindowsPTY(shell_cmd, env)
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        return UnixPTY(shell_cmd, env)
    return StubPTY(shell_cmd, env)
```

---

## Session Lifecycle

### Initialization

```python
session = SilcSession(port, shell_info, api_token)
session.pty = create_pty(shell_info.path, os.environ.copy())
session.buffer = RawByteBuffer(maxlen=65536)
```

### Startup

```python
await session.start()
# 1. Start _read_loop() task
# 2. Wait 0.5s for shell to initialize
# 3. Inject helper function
# 4. Start _garbage_collect() task
```

### Read Loop

```python
async def _read_loop():
    while not self._closed:
        data = await self.pty.read(4096)
        if data:
            self.buffer.append(data)
            self.last_output = datetime.utcnow()
            write_session_log(self.port, f"OUTPUT: {data}")
        else:
            await asyncio.sleep(0.1)
```

### Garbage Collection

```python
async def _garbage_collect():
    while not self._closed:
        await asyncio.sleep(60)
        idle = (datetime.utcnow() - self.last_access).total_seconds()
        if idle > 1800 and not self.tui_active and not self.run_lock.locked():
            await self.close()
            break
        self.rotate_logs()
```

### Shutdown

```python
async def close():
    self._closed = True
    self._read_task.cancel()
    self._gc_task.cancel()
    self.pty.kill()
    await asyncio.wait_for(self._read_task, timeout=1.0)
```

---

## Command Execution

### Sentinel Pattern

Commands are wrapped with sentinel markers for reliable output capture:

```
__SILC_BEGIN_<token>__
<command output>
__SILC_END_<token>:<exit_code>
```

### Helper Function Injection

**Bash/Zsh/Sh:**
```bash
__silc_exec() {
    printf "__SILC_BEGIN_$2__\n"
    eval "$1"
    printf "__SILC_END_$2__:%d\n" $?
}
```

**PowerShell:**
```powershell
function __silc_exec($cmd, $token) {
    Write-Host "__SILC_BEGIN_${token}__"
    Invoke-Expression $cmd
    Write-Host "__SILC_END_${token}__:$LASTEXITCODE"
}
```

**CMD:**
```batch
@echo off
echo __SILC_BEGIN_%2__
call %1
echo __SILC_END_%2__:%ERRORLEVEL%
```

### Execution Flow

```python
async def run_command(cmd: str, timeout: int = 600) -> dict:
    if self.run_lock.locked():
        return {"error": "busy", "running_cmd": self.current_run_cmd}

    async with self.run_lock:
        token = str(uuid.uuid4())[:8]
        invocation = self.shell_info.build_helper_invocation(cmd, token)
        await self.pty.write(invocation + newline)

        # Read until end sentinel or timeout
        while time < deadline:
            chunk, cursor = self.buffer.get_since(cursor)
            collected.extend(chunk)

            # Check for buffer overflow
            if len(collected) > MAX_COLLECTED_BYTES:
                await self.pty.write(b"\x03")  # Ctrl+C
                return {"error": "buffer overflow"}

            # Check for begin marker
            if begin_marker in collected:
                started = True

            # Check for end marker
            if end_marker in collected:
                return {"output": output, "exit_code": exit_code}

        return {"error": "timeout"}
```

---

## Output Buffer

### `RawByteBuffer`

**Purpose:** Store PTY output with cursor tracking for incremental reads.

**Operations:**

| Method | Description |
|--------|-------------|
| `append(data: bytes)` | Add bytes, trim to maxlen |
| `get_last(lines: int) -> List[str]` | Get last N lines |
| `get_since(cursor: int) -> Tuple[bytes, int]` | Get bytes since cursor |
| `clear()` | Reset buffer |
| `get_bytes() -> bytes` | Get all buffered bytes |

**Ring Buffer Behavior:**
- When buffer exceeds `maxlen`, oldest bytes are discarded
- `_start_offset` tracks how many bytes were discarded
- `cursor` tracks total bytes appended

---

## Output Cleaning

### `clean_output(raw_lines: Iterable[str]) -> str`

**Steps:**
1. Handle carriage returns (keep last segment after `\r`)
2. Remove ANSI/OSC/control sequences
3. Remove non-printable characters (except tabs)
4. Strip trailing whitespace
5. Collapse progress bars (keep last)
6. Collapse consecutive blank lines

**Regex Patterns:**

```python
ANSI_CONTROL_SEQUENCE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]|"      # CSI sequences
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|"  # OSC sequences
    r"\x1b[PX^_].*?\x1b\\|"        # DCS, SOS, PM, APC
    r"\x1b[@-Z\\-_]"               # Single-character ESC
)
```

---

## Shell Detection

### `detect_shell() -> ShellInfo`

**Windows:**
1. Check `PSModulePath` env var → PowerShell
2. Fallback → CMD

**Unix:**
1. Check `SHELL` env var
2. Parse basename for `zsh`, `bash`
3. Fallback → `/bin/sh`

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Single run lock | Only one `run_command()` can execute at a time |
| Sentinel detection | Commands MUST use sentinel markers for output capture |
| Buffer overflow protection | Commands exceeding 5MB MUST be interrupted |
| Timeout enforcement | Commands exceeding timeout MUST be interrupted |
| Clean shutdown | `close()` MUST cancel all background tasks |
| PTY cleanup | `kill()` MUST terminate shell process tree |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Sentinel markers | Reliable output capture across shells | High |
| Ring buffer | Memory-bounded output storage | High |
| Async read loop | Non-blocking PTY reading | High |
| Helper function injection | Shell-agnostic command execution | High |
| psutil for process killing | Cross-platform process tree termination | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/core/`
- **Entry points:** `SilcSession.__init__()`, `SilcSession.start()`
- **Key files:**
  - `session.py` — Session orchestration
  - `pty_manager.py` — PTY abstraction
  - `raw_buffer.py` — Output buffering
  - `cleaner.py` — Output cleaning
- **Related:** `silc/utils/shell_detect.py` — Shell detection

---

## Error Handling

| Error | Behavior |
|-------|----------|
| PTY creation failure | Raise exception (session creation fails) |
| Shell not found | Use fallback shell (`/bin/sh` or `cmd.exe`) |
| Read timeout | Return empty bytes |
| Write failure | Silently ignore (PTY may be closed) |
| Buffer overflow | Interrupt command, return error |
| Command timeout | Return partial output with timeout status |

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| Buffer size | 64KB default | Configurable via `maxlen` |
| Read chunk size | 4KB | Balance between latency and throughput |
| Read poll interval | 100ms | When no data available |
| GC interval | 60s | Session idle check |
| Idle timeout | 30 min | Auto-close idle sessions |
| Max collected bytes | 5MB | Prevent DoS from large output |
