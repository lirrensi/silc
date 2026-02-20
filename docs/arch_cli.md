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
├── start [--port] [--global] [--no-detach] [--token]
├── list
├── shutdown
├── killall
├── logs [--tail]
├── daemon (hidden)
└── <port>
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
        if cmd_name.isdigit():
            return PortGroup(int(cmd_name), commands=self.port_subcommands.commands)
        return super().get_command(ctx, cmd_name)
```

### `PortGroup`

```python
class PortGroup(click.Group):
    def __init__(self, port: int, **kwargs):
        self.port = port
        super().__init__(**kwargs)

    def invoke(self, ctx):
        ctx.params["port"] = self.port
        return super().invoke(ctx)
```

---

## Daemon Commands

### `silc start`

```python
@cli.command()
@click.option("--port", type=int, default=None)
@click.option("--global", "is_global", is_flag=True)
@click.option("--no-detach", is_flag=True)
@click.option("--token", type=str, default=None)
def start(port, is_global, no_detach, token):
    # 1. Show security warning if --global
    # 2. Check if daemon is running
    # 3. Start daemon if needed (detached or foreground)
    # 4. Create session via daemon API
    # 5. Print session info
```

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

---

## Session Commands

All session commands use the pattern `silc <port> <command>`.

### `silc <port> run`

```python
@cli.port_subcommands.command()
@click.argument("command", nargs=-1)
@click.option("--timeout", default=60)
def run(ctx, command, timeout):
    port = ctx.parent.params["port"]
    resp = requests.post(
        f"http://127.0.0.1:{port}/run",
        json={"command": " ".join(command), "timeout": timeout},
        timeout=120
    )
    print(resp.json().get("output", ""))
```

### `silc <port> out`

```python
@cli.port_subcommands.command()
@click.argument("lines", default=100, type=int)
def out(ctx, lines):
    port = ctx.parent.params["port"]
    resp = requests.get(f"http://127.0.0.1:{port}/out", params={"lines": lines})
    print(resp.json().get("output", ""))
```

### `silc <port> tui`

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
| Port as subcommand | `<port>` is parsed as a command group |
| HTTP communication | CLI communicates with daemon/sessions via HTTP |
| Detached daemon | Daemon runs in background by default |
| TUI binary fallback | Downloads binary if not found locally |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Click framework | Mature, well-documented | High |
| Port as subcommand | Natural `silc 20000 run` syntax | High |
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
| Session not found | Print error message |
| Port in use | Print error with existing session info |
| TUI binary not found | Print warning, suggest manual build |
| Request timeout | Print error message |
