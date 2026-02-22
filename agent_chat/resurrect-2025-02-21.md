# Plan: Session Persistence and Resurrect
_Sessions persist across daemon restarts via sessions.json; users can resurrect previous sessions with best-effort port reclamation._

---

# Checklist
- [x] Step 1: Create sessions.json persistence module
- [x] Step 2: Add to_json method to SessionEntry
- [x] Step 3: Update daemon to sync sessions.json on create/close
- [x] Step 4: Add _resurrect_sessions method to SilcDaemon
- [x] Step 5: Add /resurrect endpoint to daemon API
- [x] Step 6: Add silc resurrect CLI command
- [x] Step 7: Add silc restart CLI command
- [x] Step 8: Call resurrect on daemon startup
- [x] Step 9: Write tests

---

## Context

The daemon currently keeps all session state in memory via `SessionRegistry` (`silc/daemon/registry.py`). On shutdown, this state is lost. We need to:

1. Persist session metadata to `~/.silc/sessions.json`
2. Read and restore sessions on daemon start
3. Provide explicit `silc resurrect` command
4. Provide `silc restart` command (shutdown + start)

**Key files:**
- `silc/daemon/registry.py` — in-memory session registry
- `silc/daemon/manager.py` — daemon orchestration, session lifecycle
- `silc/utils/persistence.py` — file I/O helpers, data directory
- `silc/__main__.py` — CLI commands

**Data directory:** `DATA_DIR` from `silc/utils/persistence.py` (resolves to `~/.silc` or `%APPDATA%\silc`)

---

## Prerequisites

- Python 3.11+ environment
- Editable install (`pip install -e .`)
- All existing tests passing (`pytest tests/`)
- `silc/utils/persistence.py` exports `DATA_DIR`

---

## Scope Boundaries

**DO NOT touch:**
- `silc/core/session.py` — session internals unchanged
- `silc/api/server.py` — API endpoints unchanged (except new /resurrect)
- `silc/core/pty_manager.py` — PTY logic unchanged
- `silc/tui/` — TUI unchanged
- `silc/mcp/` — MCP unchanged

---

## Steps

### Step 1: Create sessions.json persistence module

Open `silc/utils/persistence.py`. Add the following at the end of the file (before `__all__`):

```python
# Session persistence for resurrect feature
SESSIONS_FILE = DATA_DIR / "sessions.json"


def read_sessions_json() -> list[dict]:
    """Read sessions.json, return empty list if not exists or invalid."""
    if not SESSIONS_FILE.exists():
        return []
    try:
        content = SESSIONS_FILE.read_text(encoding="utf-8")
        data = json.loads(content)
        return data.get("sessions", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_sessions_json(sessions: list[dict]) -> None:
    """Write sessions list to sessions.json atomically."""
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"sessions": sessions}
    # Write to temp file then rename for atomicity
    temp_file = SESSIONS_FILE.with_suffix(".tmp")
    try:
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.rename(SESSIONS_FILE)
    except OSError:
        # Fallback: direct write if rename fails (Windows edge case)
        SESSIONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    finally:
        try:
            temp_file.unlink()
        except OSError:
            pass


def append_session_to_json(session: dict) -> None:
    """Append a session entry to sessions.json."""
    sessions = read_sessions_json()
    # Remove any existing entry with same port or name
    sessions = [s for s in sessions if s.get("port") != session.get("port") and s.get("name") != session.get("name")]
    sessions.append(session)
    write_sessions_json(sessions)


def remove_session_from_json(port: int) -> None:
    """Remove a session entry by port from sessions.json."""
    sessions = read_sessions_json()
    sessions = [s for s in sessions if s.get("port") != port]
    write_sessions_json(sessions)
```

Add `import json` to the imports at top of file.

Update `__all__` to include:
```python
    "SESSIONS_FILE",
    "read_sessions_json",
    "write_sessions_json",
    "append_session_to_json",
    "remove_session_from_json",
```

✅ Success: `python -c "from silc.utils.persistence import read_sessions_json, write_sessions_json; print('OK')"` outputs `OK`
❌ If failed: Check for syntax errors. Ensure `import json` is added.

---

### Step 2: Add to_json method to SessionEntry

Open `silc/daemon/registry.py`. Add a `to_json` method to the `SessionEntry` dataclass:

```python
def to_json(self) -> dict:
    """Serialize session entry for persistence."""
    return {
        "port": self.port,
        "name": self.name,
        "session_id": self.session_id,
        "shell": self.shell_type,
        "created_at": self.created_at.isoformat() + "Z",
    }
```

Also add `is_global: bool = False` field to `SessionEntry` and update `to_json` to include it:

```python
@dataclass
class SessionEntry:
    port: int
    name: str
    session_id: str
    shell_type: str
    created_at: datetime
    is_global: bool = False  # Added for resurrect
    last_access: datetime = field(default_factory=datetime.utcnow)

    def to_json(self) -> dict:
        """Serialize session entry for persistence."""
        return {
            "port": self.port,
            "name": self.name,
            "session_id": self.session_id,
            "shell": self.shell_type,
            "is_global": self.is_global,
            "created_at": self.created_at.isoformat() + "Z",
        }
```

Update `SessionRegistry.add()` signature to accept `is_global`:

```python
def add(
    self, port: int, name: str, session_id: str, shell_type: str, is_global: bool = False
) -> SessionEntry:
```

And pass it when creating the entry:
```python
entry = SessionEntry(
    port=port,
    name=name,
    session_id=session_id,
    shell_type=shell_type,
    created_at=datetime.utcnow(),
    is_global=is_global,
)
```

✅ Success: `python -c "from silc.daemon.registry import SessionEntry; from datetime import datetime; e = SessionEntry(20000, 'test', 'abc', 'bash', datetime.utcnow()); print(e.to_json())"` outputs valid JSON dict
❌ If failed: Check for typos in method definition. Ensure dataclass syntax is correct.

---

### Step 3: Update daemon to sync sessions.json on create/close

Open `silc/daemon/manager.py`.

**3a. Add imports at top:**
```python
from silc.utils.persistence import (
    # ... existing imports ...
    append_session_to_json,
    remove_session_from_json,
)
```

**3b. In `create_session` endpoint, after registry.add() call, add sync:**

Find this line (approximately line 198):
```python
entry = self.registry.add(
    selected_port, session_name, session.session_id, shell_info.type
)
```

Change to:
```python
entry = self.registry.add(
    selected_port, session_name, session.session_id, shell_info.type, is_global=is_global
)
# Persist to sessions.json
append_session_to_json({
    "port": selected_port,
    "name": session_name,
    "session_id": session.session_id,
    "shell": shell_info.type,
    "is_global": is_global,
    "cwd": cwd,
    "created_at": entry.created_at.isoformat() + "Z",
})
```

**3c. In `_cleanup_session` method, after registry.remove(), add sync:**

Find this line (approximately line 604):
```python
self.registry.remove(port)
```

Add after it:
```python
# Remove from persistent registry
remove_session_from_json(port)
```

✅ Success: Start daemon, create session, check that `~/.silc/sessions.json` contains the session. Close session, check that it's removed.
❌ If failed: Add `write_daemon_log(f"Debug: sessions.json path = {SESSIONS_FILE}")` to trace file location.

---

### Step 4: Add _resurrect_sessions method to SilcDaemon

Open `silc/daemon/manager.py`. Add this method to the `SilcDaemon` class (after `_cleanup_session`):

```python
async def _resurrect_sessions(self) -> dict:
    """Restore sessions from sessions.json. Returns result summary."""
    from silc.utils.persistence import read_sessions_json

    result = {"restored": [], "failed": []}
    sessions = read_sessions_json()

    if not sessions:
        write_daemon_log("No sessions to resurrect")
        return result

    write_daemon_log(f"Resurrecting {len(sessions)} sessions...")

    for entry in sessions:
        name = entry.get("name")
        shell = entry.get("shell")
        cwd = entry.get("cwd")
        is_global = entry.get("is_global", False)
        original_port = entry.get("port")

        if not name or not shell:
            result["failed"].append({"name": name, "reason": "missing_fields"})
            continue

        # Check for name collision
        if self.registry.name_exists(name):
            result["failed"].append({"name": name, "reason": "name_collision"})
            write_daemon_log(f"Resurrect skip: name '{name}' already exists")
            continue

        # Find available port (try original first)
        port = original_port
        if port in self.sessions:
            port = find_available_port(20000, 21000)

        try:
            session_socket = self._reserve_session_socket(port, is_global)
        except OSError:
            # Port still taken, try another
            try:
                port = find_available_port(20000, 21000)
                session_socket = self._reserve_session_socket(port, is_global)
            except OSError as exc:
                result["failed"].append({"name": name, "reason": f"port_unavailable: {exc}"})
                write_daemon_log(f"Resurrect failed: port unavailable for '{name}'")
                continue

        try:
            # Get shell info
            from silc.utils.shell_detect import get_shell_info_by_type
            shell_info = get_shell_info_by_type(shell)
            if shell_info is None:
                self._close_session_socket(port)
                result["failed"].append({"name": name, "reason": f"unknown_shell: {shell}"})
                continue

            # Create session
            session = SilcSession(port, name, shell_info, cwd=cwd)
            await session.start()

            self.sessions[port] = session
            registry_entry = self.registry.add(port, name, session.session_id, shell_info.type, is_global)

            server = self._create_session_server(session, is_global=is_global)
            self.servers[port] = server

            task = asyncio.create_task(server.serve(sockets=[session_socket]))
            self._session_tasks[port] = task
            self._attach_session_task(port, task)

            status = "restored" if port == original_port else "relocated"
            result["restored"].append({
                "port": port,
                "name": name,
                "status": status,
                "original_port": original_port if status == "relocated" else None,
            })
            write_daemon_log(f"Resurrected: {name} on port {port}")

            # Update sessions.json with actual port
            append_session_to_json({
                "port": port,
                "name": name,
                "session_id": session.session_id,
                "shell": shell_info.type,
                "is_global": is_global,
                "cwd": cwd,
                "created_at": registry_entry.created_at.isoformat() + "Z",
            })

        except Exception as exc:
            self._close_session_socket(port)
            result["failed"].append({"name": name, "reason": str(exc)})
            write_daemon_log(f"Resurrect failed for '{name}': {exc}")

    return result
```

✅ Success: Method exists on SilcDaemon class, no syntax errors when importing.
❌ If failed: Check indentation. Ensure all imports are present.

---

### Step 5: Add /resurrect endpoint to daemon API

Open `silc/daemon/manager.py`. In `_create_daemon_api` method, add a new endpoint after `/restart-server`:

```python
@app.post("/resurrect")
async def resurrect():
    """Resurrect sessions from sessions.json."""
    write_daemon_log("Resurrect requested")
    result = await self._resurrect_sessions()
    return result
```

✅ Success: Start daemon, run `curl -X POST http://127.0.0.1:19999/resurrect`, get JSON response.
❌ If failed: Check that endpoint is inside `_create_daemon_api` method, properly indented under `app`.

---

### Step 6: Add silc resurrect CLI command

Open `silc/__main__.py`. Add a new command after the `restart_server` command (around line 814):

```python
@cli.command()
def resurrect() -> None:
    """Restore sessions from previous state."""
    try:
        resp = requests.post(_daemon_url("/resurrect"), timeout=30)
        resp.raise_for_status()
        result = resp.json()

        restored = result.get("restored", [])
        failed = result.get("failed", [])

        if restored:
            click.echo(f"✨ Restored {len(restored)} session(s):")
            for s in restored:
                if s.get("status") == "relocated":
                    click.echo(f"   {s['name']} → port {s['port']} (relocated from {s['original_port']})")
                else:
                    click.echo(f"   {s['name']} → port {s['port']}")

        if failed:
            click.echo(f"⚠️  Failed to restore {len(failed)} session(s):")
            for s in failed:
                click.echo(f"   {s.get('name', 'unknown')}: {s.get('reason', 'unknown reason')}")

        if not restored and not failed:
            click.echo("No sessions to resurrect")

    except requests.RequestException as e:
        click.echo(f"❌ Failed to resurrect: {e}", err=True)
```

✅ Success: Run `silc resurrect --help`, see usage. Run `silc resurrect` with daemon running, see output.
❌ If failed: Check that command is decorated with `@cli.command()`, not `@cli.port_subcommands.command()`.

---

### Step 7: Add silc restart CLI command

Open `silc/__main__.py`. Add a new command after `resurrect`:

```python
@cli.command()
def restart() -> None:
    """Shutdown daemon and immediately restart (resurrects sessions)."""
    # Graceful shutdown
    try:
        requests.post(_daemon_url("/shutdown"), timeout=35)
    except requests.RequestException:
        pass

    # Wait for daemon to stop
    if not _wait_for_daemon_stop(timeout=30):
        click.echo("⚠️  Shutdown timed out; forcing killall", err=True)
        kill_daemon(port=DAEMON_PORT, force=True, timeout=2.0)
        _wait_for_daemon_stop(timeout=5)

    click.echo("✨ Daemon stopped, restarting...")

    # Start new daemon
    _start_detached_daemon()
    started = _wait_for_daemon_start_with_logs(timeout=15)

    if not started:
        click.echo("❌ Failed to restart daemon", err=True)
        _show_daemon_error_details()
        return

    click.echo("✨ Daemon restarted (sessions resurrected from previous state)")
```

✅ Success: Run `silc restart --help`, see usage. Run `silc restart` with daemon running, see shutdown and restart.
❌ If failed: Check that `kill_daemon` and `_wait_for_daemon_stop` are imported from `silc.daemon`.

---

### Step 8: Call resurrect on daemon startup

Open `silc/daemon/manager.py`. In the `start()` method, add resurrect call after signal setup.

Find this section (around line 756):
```python
write_pidfile(os.getpid())
self._running = True
self._setup_signals()
```

Add after `self._setup_signals()`:
```python
# Resurrect persisted sessions
await self._resurrect_sessions()
```

✅ Success: Start daemon with existing sessions.json, see sessions restored in logs.
❌ If failed: Ensure `await` is present. Check that `_resurrect_sessions` is defined on `self`.

---

### Step 9: Write tests

Create `tests/test_resurrect.py`:

```python
"""Tests for session persistence and resurrect feature."""
import json
import pytest
from pathlib import Path
from silc.utils.persistence import (
    SESSIONS_FILE,
    read_sessions_json,
    write_sessions_json,
    append_session_to_json,
    remove_session_from_json,
)


def test_read_sessions_json_empty(tmp_path, monkeypatch):
    """Test reading when file doesn't exist."""
    monkeypatch.setattr("silc.utils.persistence.SESSIONS_FILE", tmp_path / "sessions.json")
    from silc.utils import persistence
    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    result = read_sessions_json()
    assert result == []


def test_write_and_read_sessions_json(tmp_path):
    """Test write/read roundtrip."""
    from silc.utils import persistence
    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    sessions = [{"port": 20000, "name": "test", "shell": "bash"}]
    write_sessions_json(sessions)

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["name"] == "test"


def test_append_session_to_json(tmp_path):
    """Test appending a session."""
    from silc.utils import persistence
    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    append_session_to_json({"port": 20000, "name": "first"})
    append_session_to_json({"port": 20001, "name": "second"})

    result = read_sessions_json()
    assert len(result) == 2


def test_append_replaces_duplicate(tmp_path):
    """Test that appending with same port/name replaces existing."""
    from silc.utils import persistence
    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    append_session_to_json({"port": 20000, "name": "original"})
    append_session_to_json({"port": 20000, "name": "replaced"})

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["name"] == "replaced"


def test_remove_session_from_json(tmp_path):
    """Test removing a session by port."""
    from silc.utils import persistence
    persistence.SESSIONS_FILE = tmp_path / "sessions.json"

    write_sessions_json([
        {"port": 20000, "name": "first"},
        {"port": 20001, "name": "second"},
    ])

    remove_session_from_json(20000)

    result = read_sessions_json()
    assert len(result) == 1
    assert result[0]["port"] == 20001
```

Run tests:
```bash
pytest tests/test_resurrect.py -v
```

✅ Success: All tests pass.
❌ If failed: Check tmp_path fixture. Ensure persistence.SESSIONS_FILE is patched correctly.

---

## Verification

1. **Create session → shutdown → start:**
   ```bash
   silc start test-session
   silc list  # note the port
   silc shutdown
   silc start another-session
   silc list  # should show test-session restored
   ```

2. **Explicit resurrect:**
   ```bash
   silc shutdown
   silc start  # starts daemon fresh
   silc resurrect  # should restore from sessions.json
   ```

3. **Restart command:**
   ```bash
   silc start restart-test
   silc restart
   silc list  # should show restart-test still present
   ```

4. **Port relocation:**
   ```bash
   silc start port-test --port 20000
   silc shutdown
   # Start something else on 20000
   python -m http.server 20000 &
   silc start  # should relocate port-test to different port
   kill %1
   ```

---

## Rollback

If critical failure, revert all changes:

```bash
git checkout -- silc/daemon/registry.py
git checkout -- silc/daemon/manager.py
git checkout -- silc/utils/persistence.py
git checkout -- silc/__main__.py
rm tests/test_resurrect.py
```

Delete sessions.json if corrupted:
```bash
rm ~/.silc/sessions.json
```
