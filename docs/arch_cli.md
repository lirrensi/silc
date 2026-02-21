# Architecture: CLI

This document describes the command-line interface. Complete enough to rewrite `silc/__main__.py` from scratch.

---

## Overview

The CLI provides user-friendly commands to interact with SILC:

- Daemon management (start, shutdown, killall)
- Session operations (run, out, status, etc.)
- TUI/Web UI launching
- Log viewing

---

## Scope Boundary

**This component owns:**
- Command parsing and validation
- HTTP client for daemon/session communication
- Output formatting
- TUI binary installation

**This component does NOT own:**
- Session logic (see [arch_core.md](arch_core.md))
- Daemon management (see [arch_daemon.md](arch_daemon.md))
- API endpoints (see [arch_api.md](arch_api.md))

**Boundary interfaces:**
- Communicates with: Daemon API (port 19999), Session API (ports 20000+)
- Exposes: `silc` console script

---

## Dependencies

### External Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `click` | CLI framework | any |
| `requests` | HTTP client | any |
| `uvicorn` | ASGI server (for daemon mode) | any |

### Internal Modules

| Module | Purpose |
|--------|---------|
| `silc/daemon/manager.py` | Daemon class |
| `silc/daemon/__init__.py` | Daemon utilities |
| `silc/tui/app.py` | Textual TUI |
| `silc/tui/installer.py` | TUI binary installer |
| `silc/utils/ports.py` | Port utilities |
| `silc/stream/cli_commands.py` | Streaming commands |

---

## Command Structure

```
silc
├── start [name] [--port] [--global] [--no-detach] [--token]
├── manager
├── list
├── shutdown
├── killall
├── restart-server
├── logs [--tail]
├── daemon (hidden)
└── <port-or-name>
    ├── run <command...> [--timeout]
    ├── out [<lines>]
    ├── in <text...>
    ├── status
    ├── interrupt
    ├── clear
    ├── reset
    ├── resize <rows> <cols>
    ├── close
    ├── kill
    ├── logs [--tail]
    ├── tui
    ├── web
    ├── open (deprecated)
    ├── stream-render <filename> [--interval]
    ├── stream-append <filename> [--interval]
    ├── stream-stop <filename>
    └── stream-status
```

---

## Command Groups

### `SilcCLI` (Custom Group)

```python
class SilcCLI(click.Group):
    port_subcommands = click.Group()

    def get_command(self, ctx, cmd_name):
        # Distinguish port (all digits) from name (contains letters)
        if cmd_name.isdigit():
            return SessionGroup(port=int(cmd_name), commands=self.port_subcommands.commands)
        elif _is_valid_name(cmd_name):
            return SessionGroup(name=cmd_name, commands=self.port_subcommands.commands)
        return super().get_command(ctx, cmd_name)
```

### `SessionGroup`

Handles both port and name identification:

```python
class SessionGroup(click.Group):
    def __init__(self, port: int | None = None, name: str | None = None, **kwargs):
        self.port = port
        self.name = name
        super().__init__(**kwargs)

    def invoke(self, ctx):
        # Resolve name to port if needed
        if self.name and not self.port:
            self.port = _resolve_name(self.name)
        ctx.params["port"] = self.port
        return super().invoke(ctx)
```

### Name Detection

```python
def _is_valid_name(s: str) -> bool:
    """Check if string is a valid session name (not a port)."""
    if s.isdigit():
        return False  # It's a port number
    # Must match [a-z][a-z0-9-]*[a-z0-9]
    return bool(re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', s.lower()))
```

### Name Resolution

```python
def _resolve_name(name: str) -> int:
    """Resolve session name to port via daemon API."""
    resp = requests.get(f"http://127.0.0.1:19999/resolve/{name}", timeout=2)
    if resp.status_code == 404:
        raise click.ClickException(f"Session '{name}' not found")
    return resp.json()["port"]
```

---

## Daemon Commands

### `silc start`

```python
@cli.command()
@click.argument("name", required=False, default=None)
@click.option("--port", type=int, default=None)
@click.option("--global", "is_global", is_flag=True)
@click.option("--no-detach", is_flag=True)
@click.option("--token", type=str, default=None)
@click.option("--shell", type=str, default=None)
@click.option("--cwd", type=str, default=None)
def start(name, port, is_global, no_detach, token, shell, cwd):
    # 1. Validate name format if provided
    # 2. Show security warning if --global
    # 3. Check if daemon is running
    # 4. Start daemon if needed (detached or foreground)
    # 5. Create session via daemon API with name
    # 6. Print session info (port, name, session_id)
```

**Name handling:**
- If `name` is provided, validate format and send to daemon
- If `name` is not provided, daemon auto-generates one
- Name collision results in error from daemon

### `silc manager`

```python
@cli.command()
def manager():
    # 1. Check if daemon is running
    # 2. Start daemon if needed (detached)
    # 3. Open browser to http://127.0.0.1:19999/
```

Opens the session manager web UI. Auto-starts the daemon if not already running.

### `silc list`

```python
@cli.command(name="list")
def list_sessions():
    resp = requests.get("http://127.0.0.1:19999/sessions")
    sessions = resp.json()
    # Format and print
```

### `silc shutdown`

```python
@cli.command()
def shutdown():
    requests.post("http://127.0.0.1:19999/shutdown", timeout=35)
    _wait_for_daemon_stop(timeout=30)
```

### `silc killall`

```python
@cli.command()
def killall():
    requests.post("http://127.0.0.1:19999/killall", timeout=3)
    kill_daemon(port=19999, force=True)
```

### `silc restart-server`

```python
@cli.command(name="restart-server")
def restart_server():
    requests.post("http://127.0.0.1:19999/restart-server", timeout=5)
```

Restarts the daemon HTTP server without killing PTY sessions. Useful for recovering from HTTP issues while keeping shells alive.

---

## Session Commands

All session commands use the pattern `silc <port-or-name> <command>`. Sessions can be identified by port number (e.g., `20000`) or by name (e.g., `my-project`).

### `silc <port-or-name> run`

```python
@cli.port_subcommands.command()
@click.argument("command", nargs=-1)
@click.option("--timeout", default=60)
def run(ctx, command, timeout):
    port = ctx.parent.params["port"]  # Resolved from name if needed
    resp = requests.post(
        f"http://127.0.0.1:{port}/run",
        json={"command": " ".join(command), "timeout": timeout},
        timeout=120
    )
    print(resp.json().get("output", ""))
```

### `silc <port-or-name> out`

```python
@cli.port_subcommands.command()
@click.argument("lines", default=100, type=int)
def out(ctx, lines):
    port = ctx.parent.params["port"]
    resp = requests.get(f"http://127.0.0.1:{port}/out", params={"lines": lines})
    print(resp.json().get("output", ""))
```

### `silc <port-or-name> tui`

```python
@cli.port_subcommands.command()
def tui(ctx):
    port = ctx.parent.params["port"]
    executable = _find_native_tui_binary()
    ws_url = f"ws://127.0.0.1:{port}/ws"
    subprocess.run([str(executable), ws_url])
```

---

## TUI Binary Management

### Binary Location

```
tui_client/dist/silc-tui-<platform>[.exe]  # Local build
~/.cache/silc/bin/silc-tui-<platform>      # Downloaded release
```

### Installation

```python
def _find_native_tui_binary() -> Path | None:
    # 1. Check local build directory
    dist_dir = _tui_dist_dir()
    if dist_dir:
        candidate = _native_tui_binary_path(dist_dir)
        if candidate.exists():
            return candidate

    # 2. Download from GitHub releases
    try:
        return ensure_native_tui_binary(progress=click.echo)
    except InstallerError:
        return None
```

### Platform Detection

```python
def _native_tui_binary_path(dist_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        filename = "silc-tui-windows.exe"
    elif sys.platform.startswith("linux"):
        filename = "silc-tui-linux"
    elif sys.platform == "darwin":
        filename = "silc-tui-macos"
    return dist_dir / filename
```

---

## Daemon Startup

### Detached Mode

```python
def _start_detached_daemon():
    python_exec = _get_daemon_python_executable()
    cmd = [python_exec, "-m", "silc", "daemon"]

    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )
        subprocess.Popen(cmd, creationflags=creationflags, ...)
    else:
        subprocess.Popen(cmd, start_new_session=True, ...)
```

### Foreground Mode

```python
@cli.command(name="daemon", hidden=True)
def run_as_daemon():
    from silc.daemon.manager import SilcDaemon
    daemon = SilcDaemon()
    asyncio.run(daemon.start())
```

---

## Utility Functions

### Daemon URL

```python
def _daemon_url(path: str) -> str:
    return f"http://127.0.0.1:19999{path}"
```

### Daemon Available Check

```python
def _daemon_available(timeout: float = 2.0) -> bool:
    try:
        requests.get(_daemon_url("/sessions"), timeout=timeout)
        return True
    except requests.RequestException:
        return False
```

### Wait for Daemon

```python
def _wait_for_daemon_start(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _daemon_available(timeout=0.5):
            return True
        time.sleep(0.3)
    return _daemon_available(timeout=0.5)
```

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Port or name as subcommand | `<port-or-name>` is parsed as a command group |
| Port = all digits | If argument is all digits, treat as port |
| Name = contains letters | If argument matches name pattern, resolve via daemon |
| HTTP communication | CLI communicates with daemon/sessions via HTTP |
| Detached daemon | Daemon runs in background by default |
| TUI binary fallback | Downloads binary if not found locally |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Click framework | Mature, well-documented | High |
| Port or name as subcommand | Natural `silc 20000 run` or `silc my-project run` syntax | High |
| Digits = port, letters = name | Unambiguous distinction | High |
| Resolve name via daemon API | Centralized name registry | High |
| HTTP client | Simple, reliable communication | High |
| Detached daemon | Background operation, no terminal required | High |
| Native TUI binary | Better performance than Python TUI | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/__main__.py`
- **Entry points:** `main()` function
- **Related:**
  - `silc/daemon/__init__.py` — Daemon utilities
  - `silc/tui/installer.py` — TUI binary installer
  - `silc/stream/cli_commands.py` — Streaming commands

---

## Error Handling

| Error | Behavior |
|-------|----------|
| Daemon not running | Start daemon automatically |
| Session not found (port) | Print error message |
| Session not found (name) | Print "Session 'name' not found" |
| Name collision | Print error from daemon |
| Invalid name format | Print error message with format rules |
| Port in use | Print error with existing session info |
| TUI binary not found | Print warning, suggest manual build |
| Request timeout | Print error message |
