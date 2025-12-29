# SILC Implementation Plan 🚀

## Project Structure

```
silc/
├── silc/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pty_manager.py   # PTY/ConPTY wrapper
│   │   ├── session.py       # Main session logic
│   │   ├── buffer.py        # Ring buffer implementation
│   │   └── cleaner.py       # Output cleaning utilities
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py        # FastAPI server
│   │   └── models.py        # Pydantic models
│   ├── tui/
│   │   ├── __init__.py
│   │   └── app.py           # Textual TUI
│   └── utils/
│       ├── __init__.py
│       ├── shell_detect.py  # Detect shell type
│       └── ports.py         # Port management
├── tests/
├── pyproject.toml
└── README.md
```

---

## Phase 1: Core Infrastructure (Week 1)

### 1.1 PTY Manager (`core/pty_manager.py`)

**Purpose**: Cross-platform PTY abstraction

```python
import sys
import asyncio
from abc import ABC, abstractmethod

class PTYBase(ABC):
    @abstractmethod
    async def read(self, size=1024): pass
    
    @abstractmethod
    async def write(self, data: bytes): pass
    
    @abstractmethod
    def resize(self, rows, cols): pass
    
    @abstractmethod
    def kill(self): pass

class UnixPTY(PTYBase):
    """Unix/Linux/Mac PTY using pty module"""
    def __init__(self, shell_cmd, env):
        import pty
        self.master, self.slave = pty.openpty()
        # Fork and exec shell
        
class WindowsPTY(PTYBase):
    """Windows PTY using pywinpty"""
    def __init__(self, shell_cmd, env):
        import winpty
        self.pty = winpty.PTY(80, 24)
        self.pty.spawn(shell_cmd, env=env)

def create_pty(shell_cmd=None, env=None):
    """Factory function"""
    if sys.platform == 'win32':
        return WindowsPTY(shell_cmd, env)
    else:
        return UnixPTY(shell_cmd, env)
```

**Key Features**:
- Auto-detect OS and use appropriate PTY
- Inherit current environment (PATH, venv, etc)
- Default to current shell (cmd.exe, pwsh, bash, zsh)
- Async read/write operations

**Dependencies**:
- `winpty` for Windows (pywinpty package)
- Built-in `pty` module for Unix

---

### 1.2 Ring Buffer (`core/buffer.py`)

**Purpose**: Memory-efficient output storage

```python
from collections import deque
from typing import Optional

class RingBuffer:
    def __init__(self, maxlen=1000):
        self.lines = deque(maxlen=maxlen)
        self.cursor = 0  # For "since" queries
        
    def append(self, data: bytes):
        """Add raw bytes, split into lines"""
        text = data.decode('utf-8', errors='replace')
        lines = text.split('\n')
        
        for line in lines:
            self.lines.append(line)
            self.cursor += 1
    
    def get_last(self, n=100) -> list[str]:
        """Get last N lines"""
        return list(self.lines)[-n:]
    
    def get_since(self, cursor: int) -> tuple[list[str], int]:
        """Get lines since cursor position"""
        # Return new lines + new cursor
        pass
    
    def clear(self):
        """Clear buffer"""
        self.lines.clear()
```

**Key Features**:
- Fixed size (1000 lines default)
- Cursor-based queries for streaming
- Thread-safe operations

---

### 1.3 Output Cleaner (`core/cleaner.py`)

**Purpose**: Clean output for agents

```python
import re

# ANSI escape code regex
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def clean_output(raw_lines: list[str]) -> str:
    """Clean output for agent consumption"""
    
    cleaned = []
    
    for line in raw_lines:
        # 1. Handle \r (carriage return) overwrites
        if '\r' in line:
            # Keep only text after last \r
            parts = line.split('\r')
            line = parts[-1]
        
        # 2. Strip ANSI codes
        line = ANSI_ESCAPE.sub('', line)
        
        # 3. Normalize line endings
        line = line.replace('\r\n', '\n').replace('\r', '\n')
        
        cleaned.append(line)
    
    # 4. Remove excessive blank lines
    result = []
    blank_count = 0
    for line in cleaned:
        if line.strip():
            result.append(line)
            blank_count = 0
        else:
            blank_count += 1
            if blank_count <= 1:
                result.append(line)
    
    return '\n'.join(result)

def collapse_progress_bars(lines: list[str]) -> list[str]:
    """Further collapse repeating progress bar patterns"""
    # Look for patterns like "█████ 60%" followed by "█████ 61%"
    # Keep only the last one
    pass
```

---

### 1.4 Shell Detection (`utils/shell_detect.py`)

**Purpose**: Detect current shell and generate correct commands

```python
import os
import sys
import re

class ShellInfo:
    def __init__(self, type: str, path: str, prompt_pattern: str):
        self.type = type  # 'bash', 'zsh', 'cmd', 'pwsh'
        self.path = path
        self.prompt_pattern = re.compile(prompt_pattern)
    
    def get_sentinel_command(self, uuid: str) -> str:
        """Generate sentinel command for 'run' detection"""
        if self.type in ['bash', 'zsh', 'sh']:
            return f'; echo "__SILC_DONE_{uuid}__:$?"'
        elif self.type == 'cmd':
            return f' & echo __SILC_DONE_{uuid}__:%ERRORLEVEL%'
        elif self.type == 'pwsh':
            return f'; echo "__SILC_DONE_{uuid}__:$LASTEXITCODE"'
        else:
            return f'; echo "__SILC_DONE_{uuid}__"'

def detect_shell() -> ShellInfo:
    """Detect current shell"""
    if sys.platform == 'win32':
        # Check if in PowerShell
        if os.environ.get('PSModulePath'):
            return ShellInfo('pwsh', 'powershell.exe', r'PS .*>')
        else:
            return ShellInfo('cmd', 'cmd.exe', r'[A-Z]:\\.*>')
    else:
        shell = os.environ.get('SHELL', '/bin/bash')
        if 'zsh' in shell:
            return ShellInfo('zsh', shell, r'.*[%#$] $')
        elif 'bash' in shell:
            return ShellInfo('bash', shell, r'.*[$#] $')
        else:
            return ShellInfo('sh', shell, r'[$#] $')
```

---

## Phase 2: Session Management (Week 1-2)

### 2.1 Main Session Class (`core/session.py`)

**Purpose**: Orchestrate PTY, buffer, and state

```python
import asyncio
import uuid
from datetime import datetime
from typing import Optional
import psutil

class SilcSession:
    def __init__(self, port: int, shell_info: ShellInfo):
        self.port = port
        self.shell_info = shell_info
        self.session_id = str(uuid.uuid4())[:8]
        
        # Core components
        self.pty = create_pty(shell_info.path, os.environ.copy())
        self.buffer = RingBuffer(maxlen=1000)
        
        # State tracking
        self.created_at = datetime.now()
        self.last_access = datetime.now()
        self.last_output = datetime.now()
        
        # Locks
        self.run_lock = asyncio.Lock()  # Only one 'run' at a time
        self.input_lock = asyncio.Lock()  # 1 sec lock on input
        
        # Background tasks
        self._read_task: Optional[asyncio.Task] = None
        self._gc_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start background reading"""
        self._read_task = asyncio.create_task(self._read_loop())
        self._gc_task = asyncio.create_task(self._garbage_collect())
    
    async def _read_loop(self):
        """Continuously read from PTY"""
        while True:
            try:
                data = await self.pty.read(4096)
                if data:
                    self.buffer.append(data)
                    self.last_output = datetime.now()
            except Exception as e:
                print(f"Read error: {e}")
                break
    
    async def _garbage_collect(self):
        """Auto-cleanup if idle too long"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            
            idle_time = (datetime.now() - self.last_access).seconds
            has_children = self._has_child_processes()
            
            if idle_time > 3600 and not has_children:
                print(f"Session {self.session_id} idle, shutting down...")
                await self.close()
                break
    
    def _has_child_processes(self) -> bool:
        """Check if shell has any child processes"""
        try:
            parent = psutil.Process(self.pty.pid)
            children = parent.children(recursive=True)
            return len(children) > 0
        except:
            return False
    
    # === API Methods ===
    
    async def write_input(self, text: str):
        """Send input to PTY (used by both TUI and API)"""
        async with self.input_lock:
            await self.pty.write(text.encode())
            await asyncio.sleep(0.1)  # Brief lock
        self.last_access = datetime.now()
    
    def get_output(self, lines=100, raw=False) -> str:
        """Get output (raw or cleaned)"""
        self.last_access = datetime.now()
        lines_list = self.buffer.get_last(lines)
        
        if raw:
            return '\n'.join(lines_list)
        else:
            return clean_output(lines_list)
    
    async def run_command(self, cmd: str, timeout=60) -> dict:
        """Run command and wait for completion"""
        
        # Only one 'run' at a time!
        if self.run_lock.locked():
            return {
                'error': 'Another run command is already executing',
                'status': 'busy'
            }
        
        async with self.run_lock:
            sentinel_uuid = str(uuid.uuid4())[:8]
            sentinel = f"__SILC_DONE_{sentinel_uuid}__"
            
            # Build command with sentinel
            full_cmd = cmd + self.shell_info.get_sentinel_command(sentinel_uuid)
            
            # Snapshot current position
            start_cursor = self.buffer.cursor
            
            # Send command
            await self.write_input(full_cmd + '\n')
            
            # Wait for sentinel or timeout
            deadline = asyncio.get_event_loop().time() + timeout
            
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.5)
                
                # Get new output
                new_lines = self.buffer.get_since(start_cursor)[0]
                new_text = '\n'.join(new_lines)
                
                # Check for sentinel
                if sentinel in new_text:
                    # Extract output before sentinel
                    output = new_text.split(sentinel)[0]
                    
                    # Try to extract exit code
                    exit_code = 0
                    if ':' in new_text:
                        try:
                            exit_code = int(new_text.split(':')[1].split()[0])
                        except:
                            pass
                    
                    return {
                        'output': clean_output(output.split('\n')),
                        'exit_code': exit_code,
                        'status': 'completed'
                    }
            
            # Timeout
            return {
                'output': clean_output(self.buffer.get_since(start_cursor)[0]),
                'status': 'timeout',
                'error': f'Command did not complete in {timeout}s'
            }
    
    def get_status(self) -> dict:
        """Get session status"""
        self.last_access = datetime.now()
        
        children = []
        try:
            parent = psutil.Process(self.pty.pid)
            children = [p.name() for p in parent.children(recursive=True)]
        except:
            pass
        
        idle_seconds = (datetime.now() - self.last_output).seconds
        
        # Check if waiting for input
        last_line = self.buffer.get_last(1)
        waiting_for_input = (
            len(last_line) > 0 and 
            any(last_line[0].strip().endswith(c) for c in [':', '?', ']'])
        )
        
        return {
            'session_id': self.session_id,
            'port': self.port,
            'alive': self._read_task and not self._read_task.done(),
            'child_processes': children,
            'has_children': len(children) > 0,
            'idle_seconds': idle_seconds,
            'waiting_for_input': waiting_for_input,
            'last_line': last_line[0] if last_line else '',
            'run_locked': self.run_lock.locked()
        }
    
    async def interrupt(self):
        """Send Ctrl+C"""
        await self.pty.write(b'\x03')
    
    async def clear_buffer(self):
        """Clear output buffer"""
        self.buffer.clear()
    
    async def close(self):
        """Graceful shutdown"""
        if self._read_task:
            self._read_task.cancel()
        if self._gc_task:
            self._gc_task.cancel()
        self.pty.kill()
    
    async def force_kill(self):
        """Hard kill"""
        self.pty.kill()
```

---

## Phase 3: API Server (Week 2)

### 3.1 FastAPI Server (`api/server.py`)

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio

class InputRequest(BaseModel):
    text: str

class RunRequest(BaseModel):
    command: str
    timeout: int = 60

# Global session registry
sessions: dict[int, SilcSession] = {}

def create_app(session: SilcSession) -> FastAPI:
    app = FastAPI(title=f"SILC Session {session.session_id}")
    
    @app.get("/status")
    async def get_status():
        return session.get_status()
    
    @app.get("/out")
    async def get_output(lines: int = 100, raw: bool = False):
        output = session.get_output(lines, raw)
        return {"output": output, "lines": len(output.split('\n'))}
    
    @app.get("/stream")
    async def stream_output():
        """SSE stream of output"""
        async def generate():
            last_cursor = session.buffer.cursor
            while True:
                new_lines, last_cursor = session.buffer.get_since(last_cursor)
                if new_lines:
                    yield f"data: {clean_output(new_lines)}\n\n"
                await asyncio.sleep(0.5)
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    @app.post("/in")
    async def send_input(req: InputRequest):
        await session.write_input(req.text)
        return {"status": "sent"}
    
    @app.post("/run")
    async def run_command(req: RunRequest):
        result = await session.run_command(req.command, req.timeout)
        return result
    
    @app.post("/interrupt")
    async def interrupt():
        await session.interrupt()
        return {"status": "interrupted"}
    
    @app.post("/clear")
    async def clear():
        await session.clear_buffer()
        return {"status": "cleared"}
    
    @app.post("/close")
    async def close():
        await session.close()
        return {"status": "closed"}
    
    @app.post("/kill")
    async def kill():
        await session.force_kill()
        return {"status": "killed"}
    
    return app
```

---

## Phase 4: CLI Interface (Week 2-3)

### 4.1 CLI Entry Point (`__main__.py`)

```python
import click
import asyncio
import uvicorn
from pathlib import Path

@click.group()
def cli():
    """SILC - Shared Interactive Linked CMD"""
    pass

@cli.command()
@click.option('--port', default=None, type=int)
@click.option('--global', 'is_global', is_flag=True)
def start(port, is_global):
    """Start a new SILC session"""
    
    # Find available port
    if not port:
        port = find_available_port(20000, 30000)
    
    # Detect shell
    shell_info = detect_shell()
    
    # Create session
    session = SilcSession(port, shell_info)
    
    # Start session
    asyncio.run(session.start())
    
    # Create API
    app = create_app(session)
    
    # Save session info
    save_session_info(port, session.session_id)
    
    # Start server
    host = "0.0.0.0" if is_global else "127.0.0.1"
    
    click.echo(f"✨ SILC session started at port {port}")
    click.echo(f"   Session ID: {session.session_id}")
    click.echo(f"   Shell: {shell_info.type}")
    click.echo(f"   Use: silc {port} open")
    
    # Start TUI in background
    asyncio.create_task(launch_tui(port))
    
    # Run server
    uvicorn.run(app, host=host, port=port)

@cli.command()
@click.argument('port', type=int)
@click.argument('lines', default=100)
def out(port, lines):
    """Get output from session"""
    import requests
    resp = requests.get(f"http://localhost:{port}/out?lines={lines}")
    print(resp.json()['output'])

@cli.command()
@click.argument('port', type=int)
@click.argument('text', nargs=-1)
def in_(port, text):
    """Send input to session"""
    import requests
    text_str = ' '.join(text)
    resp = requests.post(f"http://localhost:{port}/in", json={'text': text_str})
    print(resp.json()['status'])

@cli.command()
@click.argument('port', type=int)
@click.argument('command', nargs=-1)
@click.option('--timeout', default=60)
def run(port, command, timeout):
    """Run command and wait for result"""
    import requests
    cmd = ' '.join(command)
    resp = requests.post(
        f"http://localhost:{port}/run",
        json={'command': cmd, 'timeout': timeout}
    )
    result = resp.json()
    print(result['output'])
    if result.get('error'):
        click.echo(f"Error: {result['error']}", err=True)

@cli.command()
@click.argument('port', type=int)
def status(port):
    """Get session status"""
    import requests
    resp = requests.get(f"http://localhost:{port}/status")
    status = resp.json()
    
    click.echo(f"Session: {status['session_id']}")
    click.echo(f"Alive: {status['alive']}")
    click.echo(f"Children: {', '.join(status['child_processes']) or 'none'}")
    click.echo(f"Idle: {status['idle_seconds']}s")
    if status['waiting_for_input']:
        click.echo(f"⚠️  Waiting for input: {status['last_line']}")

@cli.command()
def list():
    """List all active sessions"""
    sessions = load_sessions()
    for port, info in sessions.items():
        click.echo(f"{port}: {info['session_id']} ({info['shell']})")

@cli.command()
@click.argument('port', type=int)
def open(port):
    """Open TUI for session"""
    asyncio.run(launch_tui(port))

if __name__ == '__main__':
    cli()
```

---

## Phase 5: TUI (Week 3)

### 5.1 Textual TUI (`tui/app.py`)

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Vertical
import requests

class TerminalOutput(Static):
    """Display terminal output"""
    pass

class SilcTUI(App):
    CSS = """
    TerminalOutput {
        height: 1fr;
        background: black;
        color: white;
        overflow-y: scroll;
    }
    Input {
        dock: bottom;
    }
    """
    
    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self.base_url = f"http://localhost:{port}"
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield TerminalOutput(id="output")
        yield Input(placeholder="Type command...")
        yield Footer()
    
    async def on_mount(self):
        """Start polling for output"""
        self.set_interval(0.5, self.update_output)
    
    async def update_output(self):
        """Fetch latest output"""
        try:
            resp = requests.get(f"{self.base_url}/out?raw=true&lines=50")
            output = resp.json()['output']
            self.query_one("#output", TerminalOutput).update(output)
        except:
            pass
    
    async def on_input_submitted(self, event: Input.Submitted):
        """Send input to session"""
        text = event.value
        requests.post(f"{self.base_url}/in", json={'text': text + '\n'})
        event.input.value = ""

async def launch_tui(port: int):
    app = SilcTUI(port)
    await app.run_async()
```

---

## Phase 6: Testing & Polish (Week 4)

### Key Tests

1. **PTY Tests**
   - Windows ConPTY works
   - Unix PTY works
   - Environment inheritance works

2. **Buffer Tests**
   - Ring buffer doesn't overflow
   - Cursor tracking works
   - Concurrent access safe

3. **Cleaning Tests**
   - ANSI codes stripped
   - \r overwrites collapsed
   - Progress bars handled

4. **Run Command Tests**
   - Sentinel detection works across shells
   - Timeout works
   - Lock prevents concurrent runs

5. **Integration Tests**
   - TUI + API both work simultaneously
   - Multiple clients can read
   - Garbage collection works

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "silc"
version = "0.1.0"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "textual>=0.44.0",
    "click>=8.1.7",
    "psutil>=5.9.6",
    "requests>=2.31.0",
    "pywinpty>=2.0.11; sys_platform == 'win32'",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Deployment

### PyInstaller Build

```bash
pyinstaller --onefile --name silc silc/__main__.py
```

Creates single `silc.exe` / `silc` binary!

---

## Usage Examples

```bash
# Start a session
silc start
# → SILC session started at port 21034

# In another terminal or from agent:
silc 21034 out               # View output
silc 21034 in "ls -la"       # Send command
silc 21034 run "npm install" # Run and wait
silc 21034 status            # Check status

# Or use API:
curl http://localhost:21034/status
curl http://localhost:21034/out?lines=50
curl -X POST http://localhost:21034/in -d '{"text": "ls\n"}'
curl -X POST http://localhost:21034/run -d '{"command": "git status"}'
```

---

## Critical Implementation Notes

### 1. Windows ConPTY
- Use `pywinpty` library
- Handle Unicode carefully
- Test with both cmd.exe and PowerShell

### 2. Run Command Lock
- MUST be async lock
- Only ONE run command at a time
- Return error if locked

### 3. Input Lock
- Brief 100ms lock on any input
- Prevents character interleaving
- TUI shows lock indicator

### 4. Garbage Collection
- Check every 60 seconds
- Criteria: idle 1hr + no children
- Save session state before cleanup

### 5. Buffer Management
- Max 1000 lines
- Bytes → UTF-8 decode with errors='replace'
- Cursor tracking for streaming
