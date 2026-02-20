# Architecture: TUI (Terminal User Interface)

This document describes the terminal user interface. Complete enough to rewrite `silc/tui/` from scratch.

---

## Overview

SILC provides two TUI options:

1. **Native TUI** — Pre-built binary (recommended)
2. **Textual TUI** — Python-based (deprecated)

The native TUI is a separate Rust binary that connects to sessions via WebSocket.

---

## Scope Boundary

**This component owns:**
- Native TUI binary installation
- Textual TUI application (deprecated)
- TUI launching logic

**This component does NOT own:**
- Session logic (see [arch_core.md](arch_core.md))
- WebSocket protocol (see [arch_api.md](arch_api.md))
- CLI parsing (see [arch_cli.md](arch_cli.md))

**Boundary interfaces:**
- Connects to: WebSocket endpoint `/ws`
- Exposes: `launch_tui(port)`, `ensure_native_tui_binary()`

---

## Native TUI

### Binary Distribution

Binaries are distributed via GitHub Releases:

```
https://github.com/lirrensi/silc/releases/latest
```

**Platform binaries:**
- `silc-tui-windows.exe` — Windows
- `silc-tui-linux` — Linux
- `silc-tui-macos` — macOS

### Installation Flow

```python
def ensure_native_tui_binary(progress: Callable[[str], None]) -> Path:
    # 1. Check cache directory
    cache_dir = platformdirs.user_cache_dir("silc") / "bin"
    
    # 2. Check for existing binary
    binary_path = cache_dir / f"silc-tui-{platform}"
    if binary_path.exists():
        return binary_path
    
    # 3. Fetch release info from GitHub API
    api_url = os.environ.get(
        "SILC_TUI_RELEASE_API",
        "https://api.github.com/repos/lirrensi/silc/releases/latest"
    )
    release = requests.get(api_url).json()
    
    # 4. Find matching asset
    asset = find_asset_for_platform(release["assets"])
    
    # 5. Download binary
    progress(f"Downloading TUI binary from {asset['browser_download_url']}")
    download_file(asset["browser_download_url"], binary_path)
    
    # 6. Make executable (Unix)
    if sys.platform != "win32":
        os.chmod(binary_path, 0o755)
    
    return binary_path
```

### Configuration

Environment variables:

| Variable | Description |
|----------|-------------|
| `SILC_TUI_BIN_DIR` | Custom binary cache directory |
| `SILC_TUI_RELEASE_REPO` | Custom GitHub repo (owner/repo) |
| `SILC_TUI_RELEASE_API` | Custom release API URL |

### Launching

```python
def _launch_native_tui_client(port: int):
    executable = _find_native_tui_binary()
    ws_url = f"ws://127.0.0.1:{port}/ws"
    subprocess.run([str(executable), ws_url])
```

---

## Textual TUI (Deprecated)

### Application

```python
class SilcTUI(App):
    CSS_PATH = "app.css"
    
    def __init__(self, port: int):
        self.port = port
        self.ws_url = f"ws://127.0.0.1:{port}/ws"
    
    async def on_mount(self):
        # Connect to WebSocket
        # Start output stream
        pass
```

### Launching

```python
async def launch_tui(port: int):
    app = SilcTUI(port)
    await app.run_async()
```

---

## WebSocket Protocol

The TUI connects to the session via WebSocket at `/ws`.

### Connection

```
ws://127.0.0.1:<port>/ws?token=<token>
```

### Server → Client Messages

**Output update:**
```json
{
  "event": "update",
  "data": "terminal output..."
}
```

**History:**
```json
{
  "event": "history",
  "data": "full terminal history..."
}
```

### Client → Server Messages

**Send input:**
```json
{
  "event": "type",
  "text": "ls -la",
  "nonewline": false
}
```

**Request history:**
```json
{
  "event": "load_history"
}
```

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| WebSocket connection | TUI MUST connect via WebSocket |
| Token for remote | Remote connections require token in query string |
| Binary caching | Downloaded binaries are cached in user cache directory |
| Platform detection | Correct binary is selected for current platform |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Native binary | Better performance, no Python overhead | High |
| GitHub Releases | Standard distribution mechanism | High |
| WebSocket protocol | Real-time bidirectional communication | High |
| Cache directory | Avoid re-downloading binaries | High |
| Deprecate Textual | Native binary is superior | High |

---

## Implementation Pointers

- **Repos/paths:** `silc/tui/`
- **Entry points:** `launch_tui(port)`, `ensure_native_tui_binary()`
- **Key files:**
  - `installer.py` — Binary installation
  - `app.py` — Textual TUI (deprecated)
- **External:** TUI binary source in separate repo

---

## Error Handling

| Error | Behavior |
|-------|----------|
| Binary not found | Download from GitHub Releases |
| Download failure | Print error, suggest manual build |
| WebSocket disconnect | Exit TUI |
| Invalid token | Connection rejected |
