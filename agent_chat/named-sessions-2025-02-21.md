# Plan: Named Sessions
_Add Docker-style names to sessions as an alternative to port-based identification._

---

# Checklist
- [x] Step 1: Create name generation module
- [x] Step 2: Update SessionEntry dataclass with name field
- [x] Step 3: Update SessionRegistry with name index
- [x] Step 4: Update SilcSession with name field
- [x] Step 5: Add /resolve/{name} endpoint to daemon API
- [x] Step 6: Update daemon POST /sessions to handle name
- [x] Step 7: Update CLI SessionGroup to handle name resolution
- [x] Step 8: Update CLI start command to accept name argument
- [x] Step 9: Update session list output to show names
- [x] Step 10: Run linters and tests

---

## Context

SILC sessions are currently identified only by port number. This plan adds Docker-style names (e.g., `happy-fox-42`) as an alternative identifier.

**Key files:**
- `silc/utils/names.py` — NEW: name generation module
- `silc/daemon/registry.py` — SessionEntry and SessionRegistry
- `silc/core/session.py` — SilcSession class
- `silc/daemon/manager.py` — Daemon API endpoints
- `silc/__main__.py` — CLI commands

**Name format:** `[a-z][a-z0-9-]*[a-z0-9]` (lowercase, starts with letter, can't end with hyphen)

**Auto-generation pattern:** `adjective-noun-number` (e.g., `happy-fox-42`)

---

## Prerequisites

- Python 3.11+ environment
- `silc` package installed in editable mode (`pip install -e .`)
- All existing tests pass (`pytest tests/`)

---

## Scope Boundaries

**OUT OF SCOPE:**
- MCP server (`silc/mcp/`) — uses port, no changes needed
- TUI client (`silc/tui/`, `tui_client/`) — no changes needed
- Stream commands (`silc/stream/`) — no changes needed
- Web UI (`static/`) — no changes needed
- Configuration (`silc/config.py`) — no new config options

---

## Steps

### Step 1: Create name generation module

Create file `silc/utils/names.py`:

```python
"""Session name generation and validation."""

from __future__ import annotations

import random
import re
from typing import Final

# ~100 adjectives for name generation
ADJECTIVES: Final[tuple[str, ...]] = (
    "happy", "sleepy", "clever", "brave", "calm", "eager", "fierce", "gentle",
    "humble", "jolly", "keen", "lively", "merry", "noble", "proud", "quick",
    "rapid", "sharp", "swift", "tidy", "upbeat", "vivid", "witty", "zesty",
    "bold", "cool", "dark", "epic", "fair", "grand", "huge", "ideal",
    "just", "kind", "light", "main", "neat", "open", "pure", "rare",
    "safe", "true", "vast", "warm", "young", "azure", "bright", "crisp",
    "deep", "fine", "glad", "high", "iron", "jet", "keen", "long",
    "mad", "new", "odd", "pink", "red", "silver", "tall", "urban",
    "violet", "white", "yellow", "amber", "blue", "cyan", "dawn", "elm",
    "frost", "gold", "hazel", "indigo", "jade", "khaki", "lime", "mint",
    "navy", "olive", "pearl", "quartz", "rose", "sage", "teal", "umber",
    "violet", "wheat", "xanthic", "yew", "zinc", "aqua", "bronze", "copper",
    "diamond", "emerald", "flame", "garnet", "hematite", "ivory", "jasper",
    "krypton", "lead", "mercury", "nickel", "opal", "platinum", "quicksilver",
)

# ~100 nouns for name generation
NOUNS: Final[tuple[str, ...]] = (
    "fox", "bear", "otter", "panda", "tiger", "eagle", "falcon", "gecko",
    "hawk", "ibis", "jaguar", "koala", "lemur", "meerkat", "newt", "ocelot",
    "penguin", "quail", "raven", "shark", "tiger", "urchin", "viper", "whale",
    "xerus", "yak", "zebra", "ant", "bee", "cat", "dog", "elk",
    "frog", "goat", "horse", "iguana", "jackal", "kangaroo", "lion", "mouse",
    "nightingale", "owl", "parrot", "rabbit", "snake", "toad", "unicorn", "vulture",
    "wolf", "ox", "ape", "bat", "crane", "deer", "eel", "flamingo",
    "giraffe", "hare", "impala", "jellyfish", "kingfisher", "lynx", "mole", "narwhal",
    "octopus", "panther", "quokka", "rhino", "seal", "turkey", "vampire", "wombat",
    "xenops", "yabby", "zorilla", "armadillo", "buffalo", "cheetah", "dolphin", "emu",
    "ferret", "gazelle", "hedgehog", "insect", "jay", "kitten", "leopard", "mongoose",
    "narwhal", "oyster", "peacock", "quail", "reindeer", "sloth", "turtle", "urchin",
    "velvet", "walrus", "xerus", "yaffle", "zebra", "albatross", "butterfly", "caterpillar",
)

# Name format: starts with letter, contains lowercase letters/numbers/hyphens, ends with alphanumeric
NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


def is_valid_name(name: str) -> bool:
    """Check if name matches the required format.

    Format: [a-z][a-z0-9-]*[a-z0-9]
    - Starts with lowercase letter
    - Contains only lowercase letters, numbers, and hyphens
    - Ends with letter or number (no trailing hyphen)
    - Minimum 2 characters
    """
    if len(name) < 2:
        return False
    return bool(NAME_PATTERN.match(name))


def generate_name() -> str:
    """Generate a random Docker-style name: adjective-noun-number.

    Example: "happy-fox-42"
    """
    adjective = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    number = random.randint(0, 99)
    return f"{adjective}-{noun}-{number}"


__all__ = ["ADJECTIVES", "NOUNS", "NAME_PATTERN", "is_valid_name", "generate_name"]
```

✅ Success: File `silc/utils/names.py` exists with all functions and constants. Running `python -c "from silc.utils.names import generate_name; print(generate_name())"` outputs a valid name.

❌ If failed: Verify file was created correctly. Check for syntax errors with `python -m py_compile silc/utils/names.py`.

---

### Step 2: Update SessionEntry dataclass with name field

Open `silc/daemon/registry.py`. Find the `SessionEntry` dataclass (approximately line 10-18). Replace the entire class with:

```python
@dataclass
class SessionEntry:
    """Registry entry for a session."""

    port: int
    name: str
    session_id: str
    shell_type: str
    created_at: datetime
    last_access: datetime = field(default_factory=datetime.utcnow)

    def update_access(self) -> None:
        """Update last_access timestamp."""
        self.last_access = datetime.utcnow()
```

✅ Success: `SessionEntry` has a `name: str` field as the second attribute.

❌ If failed: Verify the edit was applied. Check for syntax errors.

---

### Step 3: Update SessionRegistry with name index

Open `silc/daemon/registry.py`. Find the `SessionRegistry` class (approximately line 25-70). Replace the entire class with:

```python
class SessionRegistry:
    """In-memory registry of active sessions with dual index by port and name."""

    def __init__(self):
        self._sessions: Dict[int, SessionEntry] = {}
        self._name_index: Dict[str, int] = {}  # name -> port

    def add(
        self, port: int, name: str, session_id: str, shell_type: str
    ) -> SessionEntry:
        """Add a new session entry.

        Raises:
            ValueError: If name is already in use.
        """
        if name in self._name_index:
            raise ValueError(f"Session name '{name}' is already in use")

        entry = SessionEntry(
            port=port,
            name=name,
            session_id=session_id,
            shell_type=shell_type,
            created_at=datetime.utcnow(),
        )
        self._sessions[port] = entry
        self._name_index[name] = port
        return entry

    def remove(self, port: int) -> SessionEntry | None:
        """Remove a session entry."""
        entry = self._sessions.pop(port, None)
        if entry:
            self._name_index.pop(entry.name, None)
        return entry

    def get(self, port: int) -> SessionEntry | None:
        """Get a session entry by port."""
        entry = self._sessions.get(port)
        if entry:
            entry.update_access()
        return entry

    def get_by_name(self, name: str) -> SessionEntry | None:
        """Get a session entry by name."""
        port = self._name_index.get(name)
        if port is None:
            return None
        return self.get(port)

    def name_exists(self, name: str) -> bool:
        """Check if a name is already in use."""
        return name in self._name_index

    def list_all(self) -> list[SessionEntry]:
        """List all sessions sorted by port."""
        return sorted(self._sessions.values(), key=lambda s: s.port)

    def cleanup_timeout(self, timeout_seconds: int = 1800) -> list[int]:
        """Remove sessions idle longer than timeout. Returns list of ports cleaned."""
        now = datetime.utcnow()
        to_remove = []
        for port, entry in self._sessions.items():
            idle_seconds = (now - entry.last_access).total_seconds()
            if idle_seconds > timeout_seconds:
                to_remove.append(port)
        for port in to_remove:
            self.remove(port)
        return to_remove
```

✅ Success: `SessionRegistry` has `_name_index` attribute and methods: `get_by_name`, `name_exists`. The `add` method raises `ValueError` on name collision. The `remove` method cleans up both indexes.

❌ If failed: Verify the edit was applied. Run `python -c "from silc.daemon.registry import SessionRegistry; r = SessionRegistry(); print(r.name_exists('test'))"` — should output `False`.

---

### Step 4: Update SilcSession with name field

Open `silc/core/session.py`. Find the `SilcSession.__init__` method. Add `name` parameter after `port`.

Find the line `self.port = port` (approximately line 25-30). Add `self.name = name` after it.

The `__init__` signature should become:
```python
def __init__(
    self,
    port: int,
    name: str,
    shell_info: ShellInfo,
    api_token: str | None = None,
    cwd: str | None = None,
):
```

And in the body, add:
```python
self.name = name
```

Also update the `get_status` method to include `name` in the returned dict. Find the method and add `"name": self.name` to the returned dictionary.

✅ Success: `SilcSession.__init__` accepts `name` parameter. `get_status()` returns dict with `"name"` key.

❌ If failed: Verify both edits were applied. Check for syntax errors with `python -m py_compile silc/core/session.py`.

---

### Step 5: Add /resolve/{name} endpoint to daemon API

Open `silc/daemon/manager.py`.

1. Add import at the top of the file (after existing imports):
```python
from silc.utils.names import generate_name, is_valid_name
```

2. Find the daemon API router definition. Add a new endpoint after the `/sessions` GET endpoint:

```python
@daemon_api.get("/resolve/{name}")
async def resolve_session(name: str):
    """Resolve session name to session info."""
    entry = daemon.registry.get_by_name(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Session '{name}' not found")

    session = daemon.sessions.get(entry.port)
    return {
        "port": entry.port,
        "name": entry.name,
        "session_id": entry.session_id,
        "shell": entry.shell_type,
        "idle_seconds": (datetime.utcnow() - entry.last_access).total_seconds(),
        "alive": session is not None and session.pty.pid is not None,
    }
```

✅ Success: `/resolve/{name}` endpoint exists. Test with: start daemon, create session, then `curl http://127.0.0.1:19999/resolve/<name>` returns session info. Non-existent name returns 404.

❌ If failed: Check that `get_by_name` method exists on registry. Verify import statement is correct.

---

### Step 6: Update daemon POST /sessions to handle name

Open `silc/daemon/manager.py`. Find the `POST /sessions` endpoint handler.

1. Find the `SessionCreateRequest` model (likely defined near the top of the file or imported). Add `name` field:
```python
class SessionCreateRequest(BaseModel):
    port: int | None = None
    name: str | None = None
    is_global: bool = False
    token: str | None = None
    shell: str | None = None
    cwd: str | None = None
```

2. Find the endpoint handler. After validating/finding port, add name validation and generation:
```python
# After port is determined, handle name
session_name = request.name
if session_name:
    session_name = session_name.lower().strip()
    if not is_valid_name(session_name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid name format. Must match [a-z][a-z0-9-]*[a-z0-9]",
        )
    if daemon.registry.name_exists(session_name):
        raise HTTPException(
            status_code=400,
            detail=f"Session name '{session_name}' is already in use",
        )
else:
    # Auto-generate name
    for _ in range(10):  # Try 10 times to avoid collision
        session_name = generate_name()
        if not daemon.registry.name_exists(session_name):
            break
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate unique session name",
        )
```

3. Update the `registry.add()` call to include name:
```python
entry = daemon.registry.add(port, session_name, session.session_id, shell_type)
```

4. Update the response to include name:
```python
return {
    "port": port,
    "name": session_name,
    "session_id": session.session_id,
    "shell": shell_type,
}
```

5. Update the SilcSession instantiation to pass name:
```python
session = SilcSession(port, session_name, shell_info, api_token, cwd=cwd)
```

✅ Success: `POST /sessions` with `{"name": "my-project"}` creates session with that name. Without name, auto-generates one. Duplicate name returns 400. Invalid name format returns 400.

❌ If failed: Check each edit was applied. Verify `is_valid_name` and `generate_name` are imported. Test each error path manually.

---

### Step 7: Update CLI SessionGroup to handle name resolution

Open `silc/__main__.py`.

1. Rename `PortGroup` to `SessionGroup` (find the class, approximately line 216):
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

2. Add the `_resolve_name` helper function (add after `_get_error_detail` function, approximately line 205):
```python
def _resolve_name(name: str) -> int:
    """Resolve session name to port via daemon API."""
    try:
        resp = requests.get(_daemon_url(f"/resolve/{name}"), timeout=2)
        if resp.status_code == 404:
            raise click.ClickException(f"Session '{name}' not found")
        resp.raise_for_status()
        return resp.json()["port"]
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to resolve session '{name}': {e}")
```

3. Add `_is_valid_name` helper function (add after `_resolve_name`):
```python
def _is_valid_name(s: str) -> bool:
    """Check if string looks like a session name (not a port number)."""
    if s.isdigit():
        return False  # It's a port number
    from silc.utils.names import is_valid_name as validate
    return validate(s)
```

4. Update `SilcCLI.get_command` to detect names (approximately line 226):
```python
def get_command(self, ctx, cmd_name):
    if cmd_name.isdigit():
        return SessionGroup(port=int(cmd_name), commands=self.port_subcommands.commands)
    elif _is_valid_name(cmd_name):
        return SessionGroup(name=cmd_name, commands=self.port_subcommands.commands)
    return super().get_command(ctx, cmd_name)
```

✅ Success: `silc my-project status` resolves name to port and shows status. Non-existent name shows "Session 'xxx' not found" error.

❌ If failed: Check all edits were applied. Verify `_resolve_name` and `_is_valid_name` functions exist. Test with `python -c "import silc.__main__"` for import errors.

---

### Step 8: Update CLI start command to accept name argument

Open `silc/__main__.py`. Find the `start` command (approximately line 247).

1. Add `name` argument to the command signature. Change:
```python
@cli.command()
@click.option("--port", type=int, default=None, help="Port for session")
```
to:
```python
@cli.command()
@click.argument("name", required=False, default=None)
@click.option("--port", type=int, default=None, help="Port for session")
```

2. Update the function signature to accept `name`:
```python
def start(
    name: Optional[str],
    port: Optional[int],
    is_global: bool,
    no_detach: bool,
    token: Optional[str],
    shell: Optional[str],
    cwd: Optional[str],
) -> None:
```

3. Add name validation at the start of the function body (after the security warning, before daemon checks):
```python
# Validate name format if provided
if name:
    name = name.lower().strip()
    from silc.utils.names import is_valid_name
    if not is_valid_name(name):
        click.echo(
            f"❌ Invalid name format. Must match [a-z][a-z0-9-]*[a-z0-9]",
            err=True,
        )
        return
```

4. Update the payload dict to include name:
```python
payload: dict[str, object] = {}
if name is not None:
    payload["name"] = name
if port is not None:
    payload["port"] = port
```

5. Update the success output to show name:
```python
click.echo(f"✨ SILC session started at port {session['port']}")
click.echo(f"   Name: {session.get('name', 'N/A')}")
click.echo(f"   Session ID: {session['session_id']}")
click.echo(f"   Shell: {session['shell']}")
click.echo(f"   Use: silc {session.get('name', session['port'])} out")
```

✅ Success: `silc start my-project` creates session with name "my-project". `silc start` creates session with auto-generated name. Invalid name shows error. Output shows name.

❌ If failed: Verify `name` argument is added correctly. Check that payload includes name. Test with `silc start test-name` and verify daemon receives the name.

---

### Step 9: Update session list output to show names

Open `silc/__main__.py`. Find the `list_sessions` command (approximately line 696).

Update the output format to include name:
```python
click.echo("Active sessions:")
for s in sessions:
    status_icon = "✓" if s["alive"] else "✗"
    name = s.get("name", "N/A")
    click.echo(
        f"  {s['port']:5} | {name:16} | {s['session_id']:8} | {s['shell']:6} | "
        f"idle: {s['idle_seconds']:4}s {status_icon}"
    )
```

✅ Success: `silc list` shows name column. Sessions display their names (or "N/A" for old sessions without names).

❌ If failed: Verify the format string is correct. Check that daemon returns `name` in `/sessions` response.

---

### Step 10: Run linters and tests

Run all linting and type checking:
```bash
pre-commit run --all-files
```

Run the test suite:
```bash
pytest tests/ -v
```

✅ Success: All linters pass (black, isort, flake8, mypy). All tests pass. No errors.

❌ If failed: Fix any linting errors. If tests fail, investigate the failure message and fix the issue. Do not skip this step.

---

## Verification

1. **Start daemon and create named session:**
   ```bash
   silc start my-project
   ```
   Expected output shows: `Name: my-project`

2. **Use session by name:**
   ```bash
   silc my-project run "echo hello"
   silc my-project out
   ```
   Expected: "hello" is in output.

3. **List sessions shows name:**
   ```bash
   silc list
   ```
   Expected: "my-project" appears in name column.

4. **Resolve endpoint works:**
   ```bash
   curl http://127.0.0.1:19999/resolve/my-project
   ```
   Expected: JSON with port, name, session_id.

5. **Name collision rejected:**
   ```bash
   silc start my-project
   ```
   Expected: Error "Session name 'my-project' is already in use".

6. **Auto-generated name:**
   ```bash
   silc start
   ```
   Expected: Session created with name like "happy-fox-42".

---

## Rollback

If a critical step fails and cannot be recovered:

1. **Revert all changes:**
   ```bash
   git checkout -- silc/utils/names.py silc/daemon/registry.py silc/core/session.py silc/daemon/manager.py silc/__main__.py
   ```

2. **Delete new files:**
   ```bash
   rm -f silc/utils/names.py
   ```

3. **Restart daemon:**
   ```bash
   silc killall
   silc start
   ```

4. **Report the failure** with full error output from the failing step.
