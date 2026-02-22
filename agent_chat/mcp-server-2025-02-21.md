# Plan: MCP Server Implementation
_Add MCP server to SILC for AI agent integration, with shell and cwd support across all APIs._

---

# Checklist
- [x] Step 1: Add `shell` and `cwd` fields to `SessionCreateRequest` model
- [x] Step 2: Add `shell_override` and `cwd` parameters to `SilcSession.__init__`
- [x] Step 3: Add `cwd` parameter to PTY factory and implementations
- [x] Step 4: Update daemon's `create_session` endpoint to use new parameters
- [x] Step 5: Add `--shell` and `--cwd` options to CLI `start` command
- [x] Step 6: Create MCP server module structure
- [x] Step 7: Implement MCP tool: `list_sessions`
- [x] Step 8: Implement MCP tool: `start_session`
- [x] Step 9: Implement MCP tool: `close_session`
- [x] Step 10: Implement MCP tool: `get_status`
- [x] Step 11: Implement MCP tool: `read`
- [x] Step 12: Implement MCP tool: `send`
- [x] Step 13: Implement MCP tool: `send_key`
- [x] Step 14: Implement MCP tool: `run`
- [x] Step 15: Create MCP CLI entry point
- [x] Step 16: Add MCP dependency to pyproject.toml
- [x] Step 17: Run linters and fix any issues
- [x] Step 18: Manual verification

---

## Context

SILC is a Python-first CLI and FastAPI service managing terminal sessions. The codebase is in `silc/` with:

- `silc/core/session.py` — `SilcSession` class
- `silc/core/pty_manager.py` — PTY factory and implementations
- `silc/daemon/manager.py` — `SilcDaemon` and `SessionCreateRequest`
- `silc/__main__.py` — CLI entry point
- `silc/api/server.py` — FastAPI app factory

Docs were updated in `docs/product.md`, `docs/arch_mcp.md`, `docs/arch_daemon.md`, `docs/arch_core.md`, `docs/arch_index.md`.

## Prerequisites

- Python 3.11+ installed
- Virtual environment activated at `venv/` or `venv-win/`
- All existing tests passing (`pytest tests/`)
- Daemon not running (or on a port that won't conflict)

## Scope Boundaries

**OUT OF SCOPE:**
- `silc/tui/` — No TUI changes
- `silc/stream/` — No streaming changes
- `silc/utils/shell_detect.py` — No changes to shell detection logic
- Existing CLI commands other than `start` — no changes
- Web UI — no changes

---

## Steps

### Step 1: Add `shell` and `cwd` fields to `SessionCreateRequest` model

Open `silc/daemon/manager.py`. Find the `SessionCreateRequest` class (approximately line 57-60). Add two new optional fields:

```python
class SessionCreateRequest(BaseModel):
    port: int | None = None
    is_global: bool = False
    token: str | None = None
    shell: str | None = None      # NEW
    cwd: str | None = None        # NEW
```

✅ Success: File saved, `SessionCreateRequest` has 5 fields total.
❌ If failed: Stop and report the exact error from the edit.

---

### Step 2: Add `shell_override` and `cwd` parameters to `SilcSession.__init__`

Open `silc/core/session.py`. Find the `SilcSession.__init__` method (approximately line 65-91). Modify the signature and add instance variables:

Change signature from:
```python
def __init__(self, port: int, shell_info: ShellInfo, api_token: str | None = None):
```
To:
```python
def __init__(
    self,
    port: int,
    shell_info: ShellInfo,
    api_token: str | None = None,
    cwd: str | None = None,
):
```

Add `self.cwd = cwd` after `self.api_token = api_token` (approximately line 69).

✅ Success: `SilcSession.__init__` accepts `cwd` parameter and stores it as `self.cwd`.
❌ If failed: Stop and report the exact error from the edit.

---

### Step 3: Add `cwd` parameter to PTY factory and implementations

Open `silc/core/pty_manager.py`.

**3a.** Update `PTYBase` abstract class (approximately line 22-35). The `__init__` should accept `cwd`:
```python
class PTYBase(ABC):
    def __init__(self, shell_cmd: str | None, env: Mapping[str, str], cwd: str | None = None):
        self.shell_cmd = shell_cmd
        self.env = env
        self.cwd = cwd
        self.pid: int | None = None
```

**3b.** Update `UnixPTY.__init__` to pass `cwd` to subprocess.Popen. Find the `subprocess.Popen` call (approximately line 55-65). Add `cwd=self.cwd` parameter:
```python
process = subprocess.Popen(
    [shell_path],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    preexec_fn=os.setsid,
    cwd=self.cwd,  # ADD THIS
)
```

**3c.** Update `WindowsPTY.__init__` to pass `cwd`. Find the winpty spawn call (approximately line 130-145). The exact syntax depends on winpty API:
```python
# For PtyProcess.spawn:
self.process = PtyProcess.spawn(
    command,
    env=env,
    cwd=self.cwd,  # ADD THIS
)
# OR for PTY.spawn:
self.process = pty_handle.spawn(
    command,
    env=env,
    cwd=self.cwd,  # ADD THIS
)
```

**3d.** Update `StubPTY.__init__` to accept but ignore `cwd`.

**3e.** Update `create_pty` factory function (approximately line 180-198):
```python
def create_pty(
    shell_cmd: str | None, env: Mapping[str, str], cwd: str | None = None
) -> PTYBase:
    if sys.platform == "win32":
        return WindowsPTY(shell_cmd, env, cwd)
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        return UnixPTY(shell_cmd, env, cwd)
    return StubPTY(shell_cmd, env, cwd)
```

✅ Success: All PTY classes accept `cwd`, factory passes it through, tests still pass.
❌ If failed: Run `pytest tests/test_core.py -v` and report failures.

---

### Step 4: Update daemon's `create_session` endpoint to use new parameters

Open `silc/daemon/manager.py`. Find the `create_session` function inside `_create_daemon_api` (approximately line 93-161).

**4a.** Extract `shell` and `cwd` from request:
```python
@app.post("/sessions")
async def create_session(
    port: int | None = None, request: SessionCreateRequest | None = None
):
    """Create a new session."""
    selected_port = port
    is_global = False
    token: str | None = None
    shell: str | None = None      # ADD
    cwd: str | None = None        # ADD
    if selected_port is None and request:
        selected_port = request.port
        is_global = request.is_global
        token = request.token
        shell = request.shell     # ADD
        cwd = request.cwd         # ADD
```

**4b.** Handle `shell` override. Before `shell_info = detect_shell()`:
```python
    # Handle shell override
    if shell:
        from silc.utils.shell_detect import get_shell_info_by_type
        shell_info = get_shell_info_by_type(shell)
        if shell_info is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown shell type: {shell}. Supported: bash, zsh, sh, pwsh, cmd"
            )
    else:
        shell_info = detect_shell()
```

**4c.** Pass `cwd` to session creation:
```python
    session = SilcSession(selected_port, shell_info, api_token=token, cwd=cwd)
```

**4d.** Add `get_shell_info_by_type` function to `silc/utils/shell_detect.py`:
```python
def get_shell_info_by_type(shell_type: str) -> ShellInfo | None:
    """Get ShellInfo for a specific shell type, or None if unknown."""
    shell_type = shell_type.lower()
    # ... implementation based on detect_shell() patterns
```

✅ Success: Daemon API accepts `shell` and `cwd`, passes them to session.
❌ If failed: Start daemon with `python -m silc daemon`, test with curl, report error.

---

### Step 5: Add `--shell` and `--cwd` options to CLI `start` command

Open `silc/__main__.py`. Find the `start` command (approximately line 247-408).

**5a.** Add options to the command decorator:
```python
@cli.command()
@click.option("--port", type=int, default=None, help="Port for session")
@click.option("--global", "is_global", is_flag=True, help="Bind to 0.0.0.0")
@click.option("--no-detach", is_flag=True, help="Run daemon in foreground")
@click.option("--token", type=str, default=None, help="Custom API token")
@click.option("--shell", type=str, default=None, help="Shell to use (bash, zsh, pwsh, cmd)")
@click.option("--cwd", type=str, default=None, help="Working directory for session")
def start(
    port: Optional[int],
    is_global: bool,
    no_detach: bool,
    token: Optional[str],
    shell: Optional[str],   # ADD
    cwd: Optional[str],     # ADD
) -> None:
```

**5b.** Pass new options to daemon API. Find the `requests.post` call (approximately line 391):
```python
    payload: dict[str, object] = {}
    if port is not None:
        payload["port"] = port
    if is_global:
        payload["is_global"] = True
    if session_token:
        payload["token"] = session_token
    if shell:                   # ADD
        payload["shell"] = shell
    if cwd:                     # ADD
        payload["cwd"] = cwd
```

✅ Success: `silc start --shell bash --cwd /tmp` creates session in /tmp with bash.
❌ If failed: Run `silc start --shell invalid` and report error output.

---

### Step 6: Create MCP server module structure

Create directory `silc/mcp/`. Create files:

**6a.** `silc/mcp/__init__.py`:
```python
"""MCP server for SILC."""
from .server import run_mcp_server

__all__ = ["run_mcp_server"]
```

**6b.** `silc/mcp/server.py` — main MCP server (will be filled in subsequent steps).

**6c.** `silc/mcp/tools.py` — tool implementations (will be filled in subsequent steps).

✅ Success: Directory exists, files created, `import silc.mcp` succeeds.
❌ If failed: Report directory creation error or import error.

---

### Step 7: Implement MCP tool: `list_sessions`

Open `silc/mcp/tools.py`. Implement:

```python
"""MCP tool implementations."""
import requests
from typing import Any

from silc.daemon import DAEMON_PORT


def list_sessions() -> list[dict[str, Any]]:
    """List all active SILC sessions."""
    try:
        resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return []
```

✅ Success: Function returns list of session dicts or empty list on error.
❌ If failed: Test manually with daemon running, report error.

---

### Step 8: Implement MCP tool: `start_session`

Open `silc/mcp/tools.py`. Add:

```python
import os

def start_session(
    port: int | None = None,
    shell: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Create a new SILC session."""
    # Default cwd to MCP server's current directory
    if cwd is None:
        cwd = os.getcwd()

    payload: dict[str, Any] = {}
    if port is not None:
        payload["port"] = port
    if shell is not None:
        payload["shell"] = shell
    if cwd is not None:
        payload["cwd"] = cwd

    try:
        resp = requests.post(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        return {"error": str(e), "detail": _get_error_detail(e.response)}
    except requests.RequestException as e:
        return {"error": str(e)}


def _get_error_detail(response: requests.Response | None) -> str:
    """Extract error detail from response."""
    if response is None:
        return "unknown error"
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason or "unknown error"
    return data.get("detail") or data.get("error") or str(data)
```

✅ Success: Function creates session, returns port/session_id/shell or error.
❌ If failed: Test with daemon running, report error response.

---

### Step 9: Implement MCP tool: `close_session`

Open `silc/mcp/tools.py`. Add:

```python
def close_session(port: int) -> dict[str, Any]:
    """Close a SILC session."""
    try:
        resp = requests.delete(
            f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}",
            timeout=5,
        )
        if resp.status_code == 404:
            return {"error": "Session not found", "status": "not_found"}
        resp.raise_for_status()
        return {"status": "closed"}
    except requests.RequestException as e:
        return {"error": str(e)}
```

✅ Success: Function closes session, returns status or error.
❌ If failed: Test with existing session, report error.

---

### Step 10: Implement MCP tool: `get_status`

Open `silc/mcp/tools.py`. Add:

```python
def get_status(port: int) -> dict[str, Any]:
    """Get status of a SILC session."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/status",
            timeout=5,
        )
        if resp.status_code == 410:
            return {"alive": False, "error": "Session has ended"}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"alive": False, "error": str(e)}
```

✅ Success: Function returns session status dict or error.
❌ If failed: Test with existing session, report error.

---

### Step 11: Implement MCP tool: `read`

Open `silc/mcp/tools.py`. Add:

```python
def read(port: int, lines: int = 100) -> dict[str, Any]:
    """Read output from a SILC session."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{port}/out",
            params={"lines": lines},
            timeout=5,
        )
        if resp.status_code == 410:
            return {"output": "", "error": "Session has ended"}
        resp.raise_for_status()
        data = resp.json()
        return {
            "output": data.get("output", ""),
            "lines": data.get("lines", 0),
        }
    except requests.RequestException as e:
        return {"output": "", "error": str(e)}
```

✅ Success: Function returns output string or error.
❌ If failed: Test with existing session with output, report error.

---

### Step 12: Implement MCP tool: `send`

Open `silc/mcp/tools.py`. Add:

```python
import time

def send(port: int, text: str, timeout_ms: int = 5000) -> dict[str, Any]:
    """Send text to a SILC session and wait for output."""
    try:
        # Send the text
        resp = requests.post(
            f"http://127.0.0.1:{port}/in",
            data=(text + "\n").encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=5,
        )
        if resp.status_code == 410:
            return {"output": "", "alive": False, "error": "Session has ended"}
        resp.raise_for_status()

        # If timeout_ms is 0, return immediately (fire-and-forget)
        if timeout_ms == 0:
            return {"output": "", "alive": True, "lines": 0}

        # Wait and read output
        time.sleep(timeout_ms / 1000.0)
        result = read(port, lines=100)
        result["alive"] = True
        return result
    except requests.RequestException as e:
        return {"output": "", "alive": False, "error": str(e)}
```

✅ Success: Function sends text, waits, returns captured output.
❌ If failed: Test with `send(20000, "echo hello", 2000)`, report error.

---

### Step 13: Implement MCP tool: `send_key`

Open `silc/mcp/tools.py`. Add:

```python
# Key name to byte sequence mapping
KEY_SEQUENCES = {
    "ctrl+c": b"\x03",
    "ctrl+d": b"\x04",
    "ctrl+z": b"\x1a",
    "ctrl+l": b"\x0c",
    "ctrl+r": b"\x12",
    "enter": b"\r",
    "escape": b"\x1b",
    "tab": b"\t",
    "backspace": b"\x7f",
    "delete": b"\x1b[3~",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
}


def send_key(port: int, key: str) -> dict[str, Any]:
    """Send a special key to a SILC session."""
    key_lower = key.lower()
    if key_lower not in KEY_SEQUENCES:
        return {
            "output": "",
            "alive": True,
            "error": f"Unknown key: {key}. Supported: {', '.join(KEY_SEQUENCES.keys())}"
        }

    sequence = KEY_SEQUENCES[key_lower]

    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/in",
            data=sequence,
            headers={"Content-Type": "application/octet-stream"},
            timeout=5,
        )
        if resp.status_code == 410:
            return {"output": "", "alive": False, "error": "Session has ended"}
        resp.raise_for_status()

        # Brief delay then read output
        time.sleep(0.1)
        result = read(port, lines=50)
        result["alive"] = True
        return result
    except requests.RequestException as e:
        return {"output": "", "alive": False, "error": str(e)}
```

✅ Success: Function sends key sequence, returns output.
❌ If failed: Test with `send_key(20000, "ctrl+c")`, report error.

---

### Step 14: Implement MCP tool: `run`

Open `silc/mcp/tools.py`. Add:

```python
def run(port: int, command: str, timeout_ms: int = 60000) -> dict[str, Any]:
    """Execute a command with exit code capture (native shell only)."""
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/run",
            json={"command": command, "timeout": timeout_ms // 1000},
            timeout=(timeout_ms // 1000) + 10,  # Extra buffer for response
        )
        if resp.status_code == 410:
            return {"output": "", "exit_code": -1, "status": "error", "error": "Session has ended"}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"output": "", "exit_code": -1, "status": "error", "error": str(e)}
```

✅ Success: Function executes command, returns output and exit_code.
❌ If failed: Test with `run(20000, "ls -la")`, report error.

---

### Step 15: Create MCP CLI entry point

Open `silc/mcp/server.py`. Create the MCP server using the `mcp` library:

```python
"""MCP server implementation for SILC."""
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from . import tools


# Create MCP server instance
server = Server("silc-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="send",
            description="Send text to a SILC session and wait for output",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "text": {"type": "string", "description": "Text to send"},
                    "timeout_ms": {"type": "integer", "default": 5000, "description": "Wait timeout in ms"},
                },
                "required": ["port", "text"],
            },
        ),
        Tool(
            name="read",
            description="Read output from a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "lines": {"type": "integer", "default": 100, "description": "Number of lines"},
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="send_key",
            description="Send a special key (ctrl+c, enter, etc.) to a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "key": {"type": "string", "description": "Key name (ctrl+c, enter, escape, etc.)"},
                },
                "required": ["port", "key"],
            },
        ),
        Tool(
            name="list_sessions",
            description="List all active SILC sessions",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="start_session",
            description="Create a new SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Desired port (optional)"},
                    "shell": {"type": "string", "description": "Shell type (bash, zsh, pwsh, cmd)"},
                    "cwd": {"type": "string", "description": "Working directory"},
                },
            },
        ),
        Tool(
            name="close_session",
            description="Close a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="get_status",
            description="Get status of a SILC session",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                },
                "required": ["port"],
            },
        ),
        Tool(
            name="run",
            description="Execute a command with exit code capture (native shell only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "command": {"type": "string", "description": "Command to execute"},
                    "timeout_ms": {"type": "integer", "default": 60000, "description": "Timeout in ms"},
                },
                "required": ["port", "command"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool call."""
    result = {}

    if name == "send":
        result = tools.send(
            port=arguments["port"],
            text=arguments["text"],
            timeout_ms=arguments.get("timeout_ms", 5000),
        )
    elif name == "read":
        result = tools.read(
            port=arguments["port"],
            lines=arguments.get("lines", 100),
        )
    elif name == "send_key":
        result = tools.send_key(
            port=arguments["port"],
            key=arguments["key"],
        )
    elif name == "list_sessions":
        result = tools.list_sessions()
    elif name == "start_session":
        result = tools.start_session(
            port=arguments.get("port"),
            shell=arguments.get("shell"),
            cwd=arguments.get("cwd"),
        )
    elif name == "close_session":
        result = tools.close_session(port=arguments["port"])
    elif name == "get_status":
        result = tools.get_status(port=arguments["port"])
    elif name == "run":
        result = tools.run(
            port=arguments["port"],
            command=arguments["command"],
            timeout_ms=arguments.get("timeout_ms", 60000),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    import json
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run_mcp_server() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
```

**15b.** Add MCP subcommand to CLI. Open `silc/__main__.py`, add:

```python
@cli.command()
def mcp() -> None:
    """Run the MCP server for AI agent integration."""
    from silc.mcp import run_mcp_server
    asyncio.run(run_mcp_server())
```

✅ Success: `silc mcp` starts MCP server, responds to tool list requests.
❌ If failed: Run `python -m silc mcp` directly, report error output.

---

### Step 16: Add MCP dependency to pyproject.toml

Open `pyproject.toml`. Add `mcp` to dependencies:

```toml
dependencies = [
    # ... existing dependencies ...
    "mcp>=1.0.0",
]
```

Run:
```bash
pip install -e .
```

✅ Success: `pip show mcp` shows installed package.
❌ If failed: Report pip install error, try `pip install mcp` directly.

---

### Step 17: Run linters and fix any issues

Run:
```bash
pre-commit run --all-files
```

Fix any issues reported by black, isort, flake8, or mypy.

✅ Success: All linters pass with no errors.
❌ If failed: Fix issues one by one, re-run linters until clean.

---

### Step 18: Manual verification

**18a.** Start daemon:
```bash
silc start
```

**18b.** Test MCP server directly:
```bash
python -m silc mcp
```

In another terminal, test with MCP inspector or manually send JSON-RPC:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m silc mcp
```

**18c.** Test tool execution. Create a session manually:
```bash
silc start
# Note the port
silc 20000 run "echo hello"
```

Then via MCP (if using MCP inspector or client):
- `list_sessions` → should show port 20000
- `send(port=20000, text="echo from mcp")` → should return output
- `send_key(port=20000, key="ctrl+c")` → should work

✅ Success: All tools work as documented, output matches expected format.
❌ If failed: Report specific tool and error, investigate MCP server logs.

---

## Verification

1. `silc start --shell bash --cwd /tmp` creates session in /tmp with bash
2. `silc mcp` starts MCP server without errors
3. MCP `list_sessions` returns active sessions
4. MCP `send` + `read` work in SSH sessions (test: `send(port, "ssh localhost")`)
5. MCP `run` returns exit code in native shell
6. `pytest tests/` passes
7. `pre-commit run --all-files` passes

## Rollback

If critical failure during implementation:

1. Remove `silc/mcp/` directory: `rm -rf silc/mcp`
2. Revert `pyproject.toml` dependency change
3. Revert `silc/daemon/manager.py` changes: `git checkout silc/daemon/manager.py`
4. Revert `silc/core/session.py` changes: `git checkout silc/core/session.py`
5. Revert `silc/core/pty_manager.py` changes: `git checkout silc/core/pty_manager.py`
6. Revert `silc/__main__.py` changes: `git checkout silc/__main__.py`
7. Run `pip install -e .` to reinstall
8. Run `pytest tests/` to verify rollback
