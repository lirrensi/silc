# Plan: Timing & Stability Fixes
_Fix 7 issues affecting local-first usage: exception handling, memory leaks, timeouts, and race conditions._

---

# Checklist
- [x] Step 1: Fix newline escape bug in timeout fallback
- [x] Step 2: Add exception logging to session read loop
- [x] Step 3: Add exception logging to PTY manager operations
- [x] Step 4: Bound deduplicator cache to prevent memory leak
- [x] Step 5: Add connect/read timeout tuples to MCP HTTP calls
- [x] Step 6: Add max session count limit to daemon
- [x] Step 7: Add asyncio lock for session creation race condition
- [x] Step 8: Run tests and verify fixes

---

## Context

Anubis code review found 33 issues. For local-first usage, 7 are prioritized:

| Issue | File | Problem |
|-------|------|---------|
| HIGH-09 | `silc/core/session.py:398` | `split("\\n")` uses escaped literal instead of actual newline |
| HIGH-01 | `silc/core/session.py:134` | Bare `except Exception:` swallows errors silently |
| HIGH-02 | `silc/core/pty_manager.py` | Multiple bare except blocks without logging |
| CRITICAL-05 | `silc/stream/deduplicator.py:20` | `_exact_cache` grows unbounded (memory leak) |
| CRITICAL-04 | `silc/mcp/tools.py` | HTTP timeouts lack connect/read separation; can hang |
| HIGH-05 | `silc/daemon/manager.py` | No session count limit; resource exhaustion risk |
| CRITICAL-06 | `silc/daemon/manager.py:182-248` | Port reservation races with session creation |

All fixes are defensive — no API changes, no new features.

## Prerequisites

- Python 3.11+ environment with `pip install -e .` completed
- Test suite passes: `pytest tests/` runs green
- No other changes in progress

## Scope Boundaries

**OUT OF SCOPE:**
- Security fixes for remote access (timing attacks, rate limiting) — deferred to remote access phase
- TUI, Web UI, build scripts
- Any API contract changes
- Adding new features

---

## Steps

### Step 1: Fix newline escape bug in timeout fallback

Open `silc/core/session.py`. Find line 398:

```python
fallback_lines = [
    line
    for line in fallback_text.split("\\n")
    if not SILC_SENTINEL_PATTERN.search(line)
]
```

Change `"\\n"` to `"\n"`:

```python
fallback_lines = [
    line
    for line in fallback_text.split("\n")
    if not SILC_SENTINEL_PATTERN.search(line)
]
```

Save the file.

✅ Success: Line 398 now reads `fallback_text.split("\n")` (single backslash).
❌ If failed: File not found or line content differs — stop and report.

---

### Step 2: Add exception logging to session read loop

Open `silc/core/session.py`. Find lines 134-135:

```python
except Exception:
    break
```

Replace with:

```python
except Exception as e:
    write_session_log(self.port, f"Read loop error: {e}")
    break
```

Save the file.

✅ Success: Line 134-135 now logs the exception before breaking.
❌ If failed: File not found or line content differs — stop and report.

---

### Step 3: Add exception logging to PTY manager operations

Open `silc/core/pty_manager.py`.

**3a.** Find lines 153-154 (UnixPTY.kill method):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"UnixPTY.kill error: {e}")
    pass
```

**3b.** Find lines 178-179 (UnixPTY.send_sigterm method):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"UnixPTY.send_sigterm error: {e}")
    pass
```

**3c.** Find lines 191-192 (UnixPTY.send_sigkill method):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"UnixPTY.send_sigkill error: {e}")
    pass
```

**3d.** Find lines 294-295 (WindowsPTY.kill method, first except):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"WindowsPTY.kill terminate error: {e}")
    pass
```

**3e.** Find lines 303-305 (WindowsPTY.kill method, second except block):

```python
except OSError:
    pass
except Exception:
    pass
```

Replace with:

```python
except OSError:
    pass
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"WindowsPTY.kill method error: {e}")
    pass
```

**3f.** Find lines 373-374 (WindowsPTY.send_sigterm method):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"WindowsPTY.send_sigterm error: {e}")
    pass
```

**3g.** Find lines 389-390 (WindowsPTY.send_sigkill method):

```python
except Exception:
    pass
```

Replace with:

```python
except Exception as e:
    import logging
    logging.getLogger(__name__).debug(f"WindowsPTY.send_sigkill error: {e}")
    pass
```

Save the file.

✅ Success: All 7 bare except blocks now log to debug before passing.
❌ If failed: File not found or line content differs — stop and report.

---

### Step 4: Bound deduplicator cache to prevent memory leak

Open `silc/stream/deduplicator.py`.

**4a.** Find the `__init__` method (lines 11-21). Add a constant after line 19:

```python
self._exact_cache: Set[str] = set()  # For O(1) exact match checks
self._cache_max_size: int = window_size * 2  # Bound cache growth
```

**4b.** Find the `_update_cache` method (lines 109-122). Replace the entire method with:

```python
def _update_cache(self, existing_lines: List[str]) -> None:
    """Update exact match cache with existing lines.

    Args:
        existing_lines: Lines to add to cache
    """
    # Bound cache: if over limit, clear and rebuild from recent lines only
    if len(self._exact_cache) > self._cache_max_size:
        self._exact_cache.clear()

    # Limit cache to window size
    lines_to_cache = existing_lines[-self.window_size :]

    # Update cache with normalized lines
    for line in lines_to_cache:
        normalized = self.normalize_line(line)
        if normalized:
            self._exact_cache.add(normalized)
```

Save the file.

✅ Success:
- Line ~21 has `self._cache_max_size: int = window_size * 2`
- `_update_cache` method now clears cache when it exceeds `_cache_max_size`

❌ If failed: File not found or line content differs — stop and report.

---

### Step 5: Add connect/read timeout tuples to MCP HTTP calls

Open `silc/mcp/tools.py`.

**5a.** Find line 29 (list_sessions function):

```python
resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=5)
```

Replace with:

```python
resp = requests.get(f"http://127.0.0.1:{DAEMON_PORT}/sessions", timeout=(3.0, 10.0))
```

**5b.** Find line 55-59 (start_session function):

```python
resp = requests.post(
    f"http://127.0.0.1:{DAEMON_PORT}/sessions",
    json=payload,
    timeout=10,
)
```

Replace with:

```python
resp = requests.post(
    f"http://127.0.0.1:{DAEMON_PORT}/sessions",
    json=payload,
    timeout=(3.0, 30.0),
)
```

**5c.** Find lines 71-74 (close_session function):

```python
resp = requests.delete(
    f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}",
    timeout=5,
)
```

Replace with:

```python
resp = requests.delete(
    f"http://127.0.0.1:{DAEMON_PORT}/sessions/{port}",
    timeout=(3.0, 10.0),
)
```

**5d.** Find lines 86-90 (get_status function):

```python
resp = requests.get(
    f"http://127.0.0.1:{port}/status",
    timeout=5,
)
```

Replace with:

```python
resp = requests.get(
    f"http://127.0.0.1:{port}/status",
    timeout=(3.0, 10.0),
)
```

**5e.** Find lines 101-105 (resize function):

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/resize",
    params={"rows": rows, "cols": cols},
    timeout=5,
)
```

Replace with:

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/resize",
    params={"rows": rows, "cols": cols},
    timeout=(3.0, 10.0),
)
```

**5f.** Find lines 117-121 (read function):

```python
resp = requests.get(
    f"http://127.0.0.1:{port}/out",
    params={"lines": lines},
    timeout=5,
)
```

Replace with:

```python
resp = requests.get(
    f"http://127.0.0.1:{port}/out",
    params={"lines": lines},
    timeout=(3.0, 30.0),
)
```

**5g.** Find lines 138-143 (send function, POST to /in):

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/in",
    data=(text + "\n").encode("utf-8"),
    headers={"Content-Type": "text/plain; charset=utf-8"},
    timeout=5,
)
```

Replace with:

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/in",
    data=(text + "\n").encode("utf-8"),
    headers={"Content-Type": "text/plain; charset=utf-8"},
    timeout=(3.0, 10.0),
)
```

**5h.** Find lines 195-200 (send_key function):

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/in",
    data=sequence,
    headers={"Content-Type": "application/octet-stream"},
    timeout=5,
)
```

Replace with:

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/in",
    data=sequence,
    headers={"Content-Type": "application/octet-stream"},
    timeout=(3.0, 10.0),
)
```

**5i.** Find lines 217-221 (run function):

```python
resp = requests.post(
    f"http://127.0.0.1:{port}/run",
    json={"command": command, "timeout": timeout_ms // 1000},
    timeout=(timeout_ms // 1000) + 10,  # Extra buffer for response
)
```

Replace with:

```python
command_timeout = timeout_ms // 1000
resp = requests.post(
    f"http://127.0.0.1:{port}/run",
    json={"command": command, "timeout": command_timeout},
    timeout=(3.0, command_timeout + 10.0),
)
```

Save the file.

✅ Success: All 9 `requests.*` calls now use tuple timeout format `(connect, read)`.
❌ If failed: File not found or line content differs — stop and report.

---

### Step 6: Add max session count limit to daemon

Open `silc/daemon/manager.py`.

**6a.** After line 60 (`DAEMON_PORT = 19999`), add a constant:

```python
DAEMON_PORT = 19999
MAX_SESSIONS = 100  # Prevent resource exhaustion
```

**6b.** Find the `create_session` endpoint (line 131). After the port collision check (around line 155), add session count check:

Find:
```python
if selected_port in self.sessions:
    raise HTTPException(
        status_code=400, detail=f"Port {selected_port} already in use"
    )
```

After this block, add:
```python
if len(self.sessions) >= MAX_SESSIONS:
    raise HTTPException(
        status_code=503,
        detail=f"Maximum session count ({MAX_SESSIONS}) reached. Close unused sessions.",
    )
```

Save the file.

✅ Success:
- Line ~61 has `MAX_SESSIONS = 100`
- `create_session` endpoint rejects new sessions when count >= 100 with 503 status

❌ If failed: File not found or line content differs — stop and report.

---

### Step 7: Add asyncio lock for session creation race condition

Open `silc/daemon/manager.py`.

**7a.** Find the `SilcDaemon.__init__` method (around line 75). Add a lock to the instance attributes:

Find:
```python
self._daemon_server: uvicorn.Server | None = None
```

After it, add:
```python
self._session_create_lock = asyncio.Lock()  # Serialize session creation
```

**7b.** Find the `create_session` endpoint (line 131). Wrap the critical section with the lock.

Find the beginning of the endpoint body (after `session_name: str | None = None`), around line 141. Add the lock context:

Replace:
```python
if selected_port is None and request:
    selected_port = request.port
    # ... rest of the function
```

With:
```python
async with self._session_create_lock:
    if selected_port is None and request:
        selected_port = request.port
        # ... rest of the function (indent all existing code one level)
```

The lock should wrap from `if selected_port is None and request:` through the end of the function (the `return {...}` statement around line 255).

**Indentation:** All code inside the `async with self._session_create_lock:` block must be indented one additional level (4 more spaces).

Save the file.

✅ Success:
- `__init__` has `self._session_create_lock = asyncio.Lock()`
- `create_session` endpoint body is wrapped in `async with self._session_create_lock:`

❌ If failed: File not found or line content differs — stop and report.

---

### Step 8: Run tests and verify fixes

Execute the test suite:

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass. No errors related to the modified files.

If tests fail, examine the failure output. If related to changes in Steps 1-7, report the specific test failure and stop.

✅ Success: All tests pass. No failures.
❌ If failed: Report full test output. Do not proceed to commit.

---

## Verification

After all steps complete, verify:

1. **Newline fix works**: Run `pytest tests/ -k "timeout or fallback" -v` — tests pass
2. **Memory leak bounded**: Run `pytest tests/ -k "deduplicat" -v` — tests pass
3. **HTTP timeouts**: MCP tools tests pass
4. **Session limit**: Test with manual session creation (or existing test)
5. **No regressions**: Full `pytest tests/` passes

## Rollback

If a critical step fails and cannot be recovered:

```bash
git checkout -- silc/core/session.py
git checkout -- silc/core/pty_manager.py
git checkout -- silc/stream/deduplicator.py
git checkout -- silc/mcp/tools.py
git checkout -- silc/daemon/manager.py
```

Then run `pytest tests/` to confirm rollback restored original state.
