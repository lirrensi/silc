# Plan: Unify Resize Defaults and Add MCP Resize Tool
_Single source of truth for default terminal size (30×120), add resize to MCP, fix CLI defaults._

---

# Checklist
- [x] Step 1: Export size constants from session.py
- [x] Step 2: Update WindowsPTY to import constants
- [x] Step 3: Update TUI app to import constants
- [x] Step 4: Update CLI resize command to import constants
- [x] Step 5: Add resize function to MCP tools.py
- [x] Step 6: Register resize tool in MCP server.py
- [x] Step 7: Add test for session resize
- [x] Step 8: Run linters and tests

---

## Context
Resize functionality exists but has inconsistent default values:
- `silc/core/session.py:47-48` defines `DEFAULT_SCREEN_COLUMNS=120` and `DEFAULT_SCREEN_ROWS=30` — correct
- `silc/core/pty_manager.py:152` hardcodes `cols=120, rows=30` in WindowsPTY — duplicated
- `silc/tui/app.py:42-43` hardcodes `TERMINAL_COLS=120` and `TERMINAL_ROWS=30` — duplicated
- `silc/__main__.py:644-645` uses wrong defaults `24×80` for CLI resize — incorrect
- MCP server (`silc/mcp/tools.py` and `silc/mcp/server.py`) has no resize tool

Docs already updated:
- `docs/product.md` — resize defaults changed to 30×120
- `docs/arch_mcp.md` — resize tool documented

## Prerequisites
- Python 3.11+ installed
- Project installed in editable mode: `pip install -e .[test]`
- `silc` package importable
- `tests/` directory exists

## Scope Boundaries
- Do NOT modify `silc/api/server.py` — resize endpoint already works
- Do NOT modify `silc/daemon/` — not related to resize
- Do NOT modify web UI or Rust TUI client
- Do NOT modify `docs/` — already updated

---

## Steps

### Step 1: Export size constants from session.py
Open `silc/core/session.py`. Find lines 47-48:
```python
DEFAULT_SCREEN_COLUMNS = 120
DEFAULT_SCREEN_ROWS = 30
```
These constants already exist. Verify they are in the `__all__` list at the bottom of the file. If not present, add them:
```python
__all__ = ["SilcSession", "DEFAULT_SCREEN_COLUMNS", "DEFAULT_SCREEN_ROWS"]
```

✅ Success: `DEFAULT_SCREEN_COLUMNS` and `DEFAULT_SCREEN_ROWS` are exported from `silc.core.session`
❌ If failed: Check file syntax with `python -m py_compile silc/core/session.py`

### Step 2: Update WindowsPTY to import constants
Open `silc/core/pty_manager.py`. At line 152, find:
```python
self._pty_handle = winpty_module.PTY(cols=120, rows=30)
```
Replace with:
```python
from silc.core.session import DEFAULT_SCREEN_COLUMNS, DEFAULT_SCREEN_ROWS
```
Add this import at the top of the file (around line 11, after other imports). Then change line 152 to:
```python
self._pty_handle = winpty_module.PTY(cols=DEFAULT_SCREEN_COLUMNS, rows=DEFAULT_SCREEN_ROWS)
```

✅ Success: File compiles with `python -m py_compile silc/core/pty_manager.py`
❌ If failed: Check import is inside the `__init__` method or at module level, avoid circular imports

### Step 3: Update TUI app to import constants
Open `silc/tui/app.py`. Find lines 42-43:
```python
TERMINAL_COLS = 120
TERMINAL_ROWS = 30
```
Delete these two lines. Add import at the top (after line 14, with other imports from silc):
```python
from silc.core.session import DEFAULT_SCREEN_COLUMNS, DEFAULT_SCREEN_ROWS
```
Then find line 99 which references `TERMINAL_ROWS, TERMINAL_COLS`:
```python
await self._send_resize(TERMINAL_ROWS, TERMINAL_COLS)
```
Replace with:
```python
await self._send_resize(DEFAULT_SCREEN_ROWS, DEFAULT_SCREEN_COLUMNS)
```

✅ Success: File compiles with `python -m py_compile silc/tui/app.py`
❌ If failed: Verify import path is correct, check for circular imports

### Step 4: Update CLI resize command to import constants
Open `silc/__main__.py`. Find lines 644-645:
```python
@click.option("--rows", type=int, default=24, help="Number of rows")
@click.option("--cols", type=int, default=80, help="Number of columns")
```
Change the defaults to:
```python
@click.option("--rows", type=int, default=30, help="Number of rows")
@click.option("--cols", type=int, default=120, help="Number of columns")
```
(These values match `DEFAULT_SCREEN_ROWS` and `DEFAULT_SCREEN_COLUMNS`. Hardcoding is acceptable here since Click decorators require compile-time defaults.)

✅ Success: File compiles with `python -m py_compile silc/__main__.py`
❌ If failed: Check syntax of click decorators

### Step 5: Add resize function to MCP tools.py
Open `silc/mcp/tools.py`. Add this function after `get_status` function (around line 96):

```python
def resize(port: int, rows: int = 30, cols: int = 120) -> dict[str, Any]:
    """Resize a SILC session terminal."""
    try:
        resp = requests.post(
            f"http://127.0.0.1:{port}/resize",
            params={"rows": rows, "cols": cols},
            timeout=5,
        )
        if resp.status_code == 410:
            return {"error": "Session has ended", "status": "not_found"}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}
```

Then update the `__all__` list at the bottom (line 219-229) to include `"resize"`:
```python
__all__ = [
    "list_sessions",
    "start_session",
    "close_session",
    "get_status",
    "resize",
    "read",
    "send",
    "send_key",
    "run",
    "KEY_SEQUENCES",
]
```

✅ Success: File compiles with `python -m py_compile silc/mcp/tools.py`
❌ If failed: Check for typos in function definition, verify `requests` import exists

### Step 6: Register resize tool in MCP server.py
Open `silc/mcp/server.py`. Find the `list_tools()` function (line 18). After the `get_status` Tool definition (around line 114), add a new Tool:

```python
        Tool(
            name="resize",
            description="Resize a SILC session terminal dimensions",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Session port"},
                    "rows": {
                        "type": "integer",
                        "default": 30,
                        "description": "Number of rows",
                    },
                    "cols": {
                        "type": "integer",
                        "default": 120,
                        "description": "Number of columns",
                    },
                },
                "required": ["port"],
            },
        ),
```

Then find the `call_tool()` function (line 135). After the `get_status` handler (around line 167), add:

```python
    elif name == "resize":
        result = tools.resize(
            port=arguments["port"],
            rows=arguments.get("rows", 30),
            cols=arguments.get("cols", 120),
        )
```

✅ Success: File compiles with `python -m py_compile silc/mcp/server.py`
❌ If failed: Check indentation matches surrounding code, verify `tools` import exists

### Step 7: Add test for session resize
Create a new test file `tests/test_resize.py`:

```python
"""Tests for resize functionality."""
import sys

import pytest

from silc.core.session import SilcSession, DEFAULT_SCREEN_ROWS, DEFAULT_SCREEN_COLUMNS
from silc.utils.shell_detect import detect_shell

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Resize tests have Windows PTY interaction issues",
)


@pytest.mark.asyncio
async def test_session_default_size() -> None:
    """Verify session is created with default dimensions."""
    shell_info = detect_shell()
    try:
        session = SilcSession(port=20050, shell_info=shell_info)
    except OSError as exc:
        pytest.skip(f"PTY not available: {exc}")

    try:
        await session.start()
        assert session.screen_rows == DEFAULT_SCREEN_ROWS
        assert session.screen_columns == DEFAULT_SCREEN_COLUMNS
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_session_resize() -> None:
    """Verify resize updates session dimensions."""
    shell_info = detect_shell()
    try:
        session = SilcSession(port=20051, shell_info=shell_info)
    except OSError as exc:
        pytest.skip(f"PTY not available: {exc}")

    try:
        await session.start()

        # Resize to custom dimensions
        session.resize(rows=40, cols=160)
        assert session.screen_rows == 40
        assert session.screen_columns == 160

        # Resize to minimum
        session.resize(rows=1, cols=1)
        assert session.screen_rows == 1
        assert session.screen_columns == 1

        # Resize with invalid values (should clamp to minimum 1)
        session.resize(rows=0, cols=0)
        assert session.screen_rows == 1
        assert session.screen_columns == 1
    finally:
        await session.close()
```

✅ Success: File created, syntax valid with `python -m py_compile tests/test_resize.py`
❌ If failed: Check pytest import, verify test function syntax

### Step 8: Run linters and tests
Execute from project root:
```bash
pre-commit run --all-files
```

Expected: All checks pass (black, isort, flake8, mypy).

Then run tests:
```bash
pytest tests/test_resize.py -v
```

Expected: Tests pass or are skipped on Windows.

Then run full test suite:
```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass.

✅ Success: Linters pass, tests pass
❌ If failed: Fix linting errors first, then address test failures. Do not skip this step.

---

## Verification
1. Run `python -c "from silc.core.session import DEFAULT_SCREEN_ROWS, DEFAULT_SCREEN_COLUMNS; print(f'{DEFAULT_SCREEN_ROWS}x{DEFAULT_SCREEN_COLUMNS}')"` — should output `30x120`
2. Run `silc <port> resize --help` — should show default values 30 and 120
3. Run `pytest tests/test_resize.py -v` — tests pass
4. Verify MCP tool: `python -c "from silc.mcp.tools import resize; print(resize.__doc__)"` — should print docstring

## Rollback
If critical failure occurs:
1. `git checkout -- silc/core/session.py silc/core/pty_manager.py silc/tui/app.py silc/__main__.py silc/mcp/tools.py silc/mcp/server.py`
2. Delete `tests/test_resize.py` if created
3. Re-run `pre-commit run --all-files` to verify rollback
