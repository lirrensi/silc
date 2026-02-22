# SILC Core Package Code Review Findings

**Date**: 2026-02-22
**Reviewer**: Anubis (Code Review Agent)
**Scope**: `silc/` Python package — core, daemon, api, mcp, stream, utils modules

---

## CRITICAL Issues (Must Fix Before Ship)

### CRITICAL-01 — Token Comparison Uses Non-Constant-Time Equality
**Location**: `silc/api/server.py:64-66`
**Problem**: Token comparison uses `!=` operator which is not constant-time. Attackers can measure response time to brute-force tokens character-by-character.
**Impact**: Timing attacks can recover API tokens, leading to unauthorized remote code execution.
**Fix**: Use `secrets.compare_digest()` for all secret/token comparisons:
```python
import secrets
if not secrets.compare_digest(provided, token):
    raise HTTPException(status_code=403, detail="Invalid API token")
```

---

### CRITICAL-02 — WebSocket Token Verification Also Non-Constant-Time
**Location**: `silc/api/server.py:76-77`
**Problem**: WebSocket token check uses `==` operator directly.
**Impact**: Same timing attack vulnerability as CRITICAL-01.
**Fix**: Use `secrets.compare_digest()`:
```python
return secrets.compare_digest(provided or "", token or "")
```

---

### CRITICAL-03 — No Rate Limiting on Authentication Endpoints
**Location**: `silc/api/server.py` (all endpoints), `silc/daemon/manager.py` (daemon API)
**Problem**: No rate limiting on `/run`, `/in`, daemon `/sessions` creation, or any authentication endpoints. Attackers can brute-force tokens or hammer the API.
**Impact**: Brute-force token recovery, denial of service, resource exhaustion.
**Fix**: Implement rate limiting per-client (IP or token) with exponential backoff. Use a sliding window algorithm. At minimum:
- Auth failures: 5 attempts per minute per IP
- API calls: 100 requests per minute per IP
- Session creation: 10 per minute per IP

---

### CRITICAL-04 — Missing Timeout on HTTP Client Calls in MCP Tools
**Location**: `silc/mcp/tools.py:29, 55-59, 71-74, 86-90, 117-120, 138-145, 195-200, 218-220`
**Problem**: All HTTP requests have fixed `timeout=5` or `timeout=10` but no connect/read timeout separation. Some have no timeout at all on the `requests.post` calls that could hang indefinitely if the server stops responding.
**Impact**: Blocking calls hang indefinitely, causing MCP server to freeze and AI agents to become unresponsive.
**Fix**: Always use tuple timeout `(connect_timeout, read_timeout)`:
```python
requests.get(url, timeout=(3.0, 30.0))
```

---

### CRITICAL-05 — Unbounded Collection Growth in Deduplicator Cache
**Location**: `silc/stream/deduplicator.py:20`
**Problem**: `_exact_cache` is a `Set[str]` that only grows (via `add()`) but is never bounded or cleared between sessions. The `window_size` limits the lines processed per call, but the cache accumulates across all calls indefinitely.
**Impact**: Memory leak that grows unbounded over time, eventually consuming all available memory in long-running sessions.
**Fix**: Bound the cache size and implement LRU eviction:
```python
from functools import lru_cache
# Or use a bounded set with max size
if len(self._exact_cache) > self.window_size * 2:
    # Clear and rebuild from recent lines
    self._exact_cache.clear()
```

---

### CRITICAL-06 — Potential Race Condition in Session Creation
**Location**: `silc/daemon/manager.py:182-248`
**Problem**: Port reservation via `_reserve_session_socket()` happens before session creation. If session creation fails (line 247), the socket is closed in exception handler but the port might be re-acquired by another concurrent request during the gap.
**Impact**: Two sessions could be assigned the same port, causing binding failures or traffic routing to wrong session.
**Fix**: Use a lock around the entire port reservation + session creation sequence, or use atomic port reservation with timeout.

---

## HIGH Priority Issues (Fix Soon)

### HIGH-01 — Exception Swallowing in Read Loop
**Location**: `silc/core/session.py:134-135`
**Problem**: Bare `except Exception:` swallows all exceptions without logging or re-raising. The read loop silently dies on any error.
**Impact**: Debugging nightmares. Session can die silently without any indication why. Critical errors are hidden.
**Fix**: At minimum, log the exception:
```python
except Exception as e:
    write_session_log(self.port, f"Read loop error: {e}")
    break
```

---

### HIGH-02 — Exception Swallowing in PTY Operations
**Location**: `silc/core/pty_manager.py:127-128, 134-135, 153-154, 178-179, 191-192, 294-295, 303-305, 373-374, 389-390`
**Problem**: Multiple bare `except Exception:` blocks that silently swallow errors. PTY operations can fail silently.
**Impact**: PTY state corruption, zombie processes, resource leaks without any diagnostic trail.
**Fix**: Log exceptions at minimum. For recoverable errors, use specific exception types.

---

### HIGH-03 — No Input Validation on Command Before Execution
**Location**: `silc/core/session.py:274-406`
**Problem**: `run_command()` accepts any string as a command without validation. Commands with embedded newlines could inject additional commands. Command length is not limited.
**Impact**: Command injection through crafted input (e.g., `ls; rm -rf /`). Newline injection can execute unintended commands.
**Fix**:
- Strip or reject embedded newlines in commands
- Set a maximum command length
- Document that commands run with user's full permissions

---

### HIGH-04 — Logging Potentially Contains Sensitive Data
**Location**: `silc/core/session.py:117-119, 297`
**Problem**: Full terminal output and commands are logged to session logs. This could include passwords, API keys, or other secrets typed in the shell.
**Impact**: Secret exposure through log files. Anyone with file system access can read secrets from logs.
**Fix**: Sanitize logs or add a privacy mode. At minimum, document this behavior clearly:
```python
# WARNING: Logs may contain sensitive data including passwords and API keys
```

---

### HIGH-05 — No Maximum Session Count Limit
**Location**: `silc/daemon/manager.py:131-261`
**Problem**: No limit on number of concurrent sessions. An attacker or buggy client can create unlimited sessions, exhausting file descriptors and memory.
**Impact**: Resource exhaustion leading to system instability.
**Fix**: Implement a maximum session count (e.g., 100) and reject new sessions when limit is reached.

---

### HIGH-06 — `time.sleep()` in Hot Path
**Location**: `silc/mcp/tools.py:153`
**Problem**: `send()` uses blocking `time.sleep(timeout_ms / 1000.0)` which blocks the entire async event loop.
**Impact**: Blocks the MCP server from processing other requests during the wait period.
**Fix**: Use `asyncio.sleep()` in async context, or document that `send` is a blocking call for synchronous MCP usage.

---

### HIGH-07 — Missing Cleanup of Temp Helper Script
**Location**: `silc/utils/shell_detect.py:76-88`
**Problem**: `_ensure_cmd_helper()` creates a batch script in temp directory but never deletes it. On multi-user systems, this could be modified by other users before execution.
**Impact**: Potential for privilege escalation if another user modifies the script. Also temp directory pollution.
**Fix**:
- Create script with restricted permissions (0700)
- Clean up on session close
- Or embed the script content inline

---

### HIGH-08 — Global Mutable State in Config Module
**Location**: `silc/config.py:297-298`
**Problem**: Global `_config` variable is mutable and accessed without locks. `reload_config()` can race with `get_config()`.
**Impact**: Race conditions in multi-threaded/multi-async context could return inconsistent config.
**Fix**: Use a lock around config access, or make config immutable after initialization.

---

### HIGH-09 — Inconsistent Newline Handling in Timeout Fallback
**Location**: `silc/core/session.py:398`
**Problem**: Fallback lines are split on `\\n` (escaped backslash-n) instead of actual newline character `\n`.
**Impact**: When command times out, the fallback output is incorrectly parsed, resulting in garbled output.
**Fix**:
```python
fallback_lines = [
    line
    for line in fallback_text.split("\n")  # Not "\\n"
    if not SILC_SENTINEL_PATTERN.search(line)
]
```

---

### HIGH-10 — Missing Validation on Session Name in Registry
**Location**: `silc/daemon/registry.py:45-71`
**Problem**: `SessionRegistry.add()` raises `ValueError` on name collision but doesn't validate the name format. Invalid names could be added directly via registry bypassing the API validation.
**Impact**: Inconsistent behavior if registry is used directly. Potential for names that break CLI resolution.
**Fix**: Validate name format in `SessionRegistry.add()` as well, or make validation centralized.

---

## MEDIUM Priority Issues (Should Fix)

### MEDIUM-01 — Hardcoded Credentials Warning Exposed to Clients
**Location**: `silc/daemon/manager.py:231-246`
**Problem**: When `--global` is used, the daemon logs multiple WARNING messages but does not enforce token requirement. The warnings are good but token is still optional.
**Impact**: Users might run `--global` without a token, exposing their machine to the network without authentication.
**Fix**: Make token mandatory when `--global` is used, or refuse to start without explicit acknowledgment.

---

### MEDIUM-02 — Empty Catch Block in StreamingService
**Location**: `silc/stream/streaming_service.py:197-198`
**Problem**: `except Exception as e:` logs the error but doesn't propagate it or indicate failure to the caller.
**Impact**: Silent failures in file operations that callers won't know about.
**Fix**: Either propagate the exception or return an error indicator.

---

### MEDIUM-03 — Potential Unicode Decode Errors Not Handled
**Location**: `silc/core/session.py:118, 171, 229, 371`
**Problem**: `decode('utf-8', errors='replace')` silently replaces invalid UTF-8 with replacement characters. While not crashing, this corrupts binary output.
**Impact**: Binary output from commands (images, compressed files) is silently corrupted.
**Fix**: Document that this is a text-oriented terminal. For binary-safe output, consider a raw mode.

---

### MEDIUM-04 — No Graceful Degradation When psutil Fails
**Location**: `silc/daemon/pidfile.py:72-74, 123-126`, `silc/core/pty_manager.py` (multiple locations)
**Problem**: When `psutil` operations fail (e.g., permission denied, process gone), exceptions are caught but code continues without indication.
**Impact**: Process cleanup might fail silently, leaving zombie processes or orphaned PTYs.
**Fix**: Log psutil failures. Consider fallback strategies.

---

### MEDIUM-05 — Constants Scattered Across Files
**Location**: `silc/core/session.py:42-61`, `silc/config.py`
**Problem**: Configuration constants like `MAX_COLLECTED_BYTES`, `DEFAULT_COMMAND_TIMEOUT`, `GC_INTERVAL_SECONDS` are defined in `session.py` instead of using the config system.
**Impact**: These values cannot be configured without code changes, despite having a config system.
**Fix**: Move these constants to config or use config values with fallbacks.

---

### MEDIUM-06 — `datetime.utcnow()` Deprecated in Python 3.12+
**Location**: `silc/core/session.py:81-83`, `silc/daemon/registry.py:20, 66`, etc.
**Problem**: `datetime.utcnow()` is deprecated in Python 3.12+. It returns naive datetime objects which can cause issues.
**Impact**: Future deprecation warnings, potential timezone-related bugs.
**Fix**: Use `datetime.now(timezone.utc)`:
```python
from datetime import datetime, timezone
self.created_at = datetime.now(timezone.utc)
```

---

### MEDIUM-07 — No Validation of `cwd` Parameter
**Location**: `silc/daemon/manager.py:196-197`
**Problem**: `cwd` is passed directly to session creation without validating it exists or is accessible.
**Impact**: Session creation fails with cryptic error if cwd doesn't exist.
**Fix**: Validate cwd exists and is a directory before creating session:
```python
if cwd and not Path(cwd).is_dir():
    raise HTTPException(status_code=400, detail=f"Working directory does not exist: {cwd}")
```

---

### MEDIUM-08 — Potential Memory Leak in StreamingService
**Location**: `silc/stream/streaming_service.py:27`
**Problem**: `LineDeduplicator` is created once per `StreamingService` but its cache grows unbounded (see CRITICAL-05). Also, `active_streams` dict could grow if tasks fail without proper cleanup.
**Impact**: Memory growth over time in long-running sessions with streaming enabled.
**Fix**: Reset deduplicator cache between stream starts, or create new deduplicator per stream.

---

### MEDIUM-09 — Missing `__slots__` on High-Instantiation Classes
**Location**: `silc/daemon/registry.py:11-35` (`SessionEntry`), `silc/utils/shell_detect.py:16-89` (`ShellInfo`)
**Problem**: These dataclasses are instantiated frequently but don't use `__slots__`.
**Impact**: Higher memory usage than necessary (per-instance `__dict__`).
**Fix**: Add `slots=True` to dataclass decorator in Python 3.10+:
```python
@dataclass(slots=True)
class SessionEntry:
    ...
```

---

### MEDIUM-10 — Inconsistent Error Response Format
**Location**: `silc/api/server.py`, `silc/daemon/manager.py`
**Problem**: Some endpoints return `{"error": "...", "status": "..."}` (session.py), others return `{"detail": "..."}` (FastAPI HTTPException), and others return raw exceptions.
**Impact**: Clients must handle multiple error response formats. Inconsistent API contract.
**Fix**: Standardize on a single error response format across all endpoints:
```python
{"error": "message", "code": "ERROR_CODE", "details": {...}}
```

---

## LOW Priority Issues (Nice to Have)

### LOW-01 — Unused Variable `consecutive_empty_reads`
**Location**: `silc/core/session.py:109`
**Problem**: Variable is initialized and incremented but the value after the loop exit is never used meaningfully.
**Impact**: Code clarity, minor inefficiency.
**Fix**: Either use the count for diagnostics or remove it.

---

### LOW-02 — Magic Numbers Without Constants
**Location**: `silc/core/session.py:104, 131, 142`, `silc/daemon/manager.py:339`
**Problem**: Numbers like `0.5`, `0.1`, `60`, `30.0` appear without named constants.
**Impact**: Code readability and maintainability.
**Fix**: Define named constants at module level.

---

### LOW-03 — Long Functions That Could Be Split
**Location**:
- `silc/core/session.py:274-406` (`run_command` - 132 lines)
- `silc/daemon/manager.py:95-427` (`_create_daemon_api` - 332 lines)
- `silc/__main__.py:306-475` (`start` - 169 lines)

**Problem**: Functions exceeding 100 lines are harder to understand and test.
**Impact**: Maintainability, testability.
**Fix**: Extract logical sections into helper functions.

---

### LOW-04 — Commented-Out Code
**Location**: `silc/api/server.py:229`
**Problem**: Comment mentions removed endpoints. Should be removed.
**Impact**: Code clutter, potential confusion.
**Fix**: Remove the comment or document why the endpoints were removed.

---

### LOW-05 — Missing Type Hints on Some Functions
**Location**: `silc/stream/api_endpoints.py:13`, various locations
**Problem**: Some functions use `Any` or lack return type hints.
**Impact**: Reduced type safety, harder IDE navigation.
**Fix**: Add explicit type hints to all public functions.

---

### LOW-06 — Re-importing Modules Inside Functions
**Location**: `silc/daemon/manager.py:186-187, 527, 911`, `silc/core/pty_manager.py:142-143, 266, 354, 361, 378`
**Problem**: `import psutil` and other imports happen inside functions rather than at module level.
**Impact**: Minor performance hit, harder to trace dependencies.
**Fix**: Move imports to module level where possible, or document why lazy import is needed (e.g., optional dependency).

---

### LOW-07 — Verbose Boolean Expression
**Location**: `silc/core/session.py:415`
**Problem**: `bool(last_line and last_line.strip().endswith((":?", "]")))` is complex and inline.
**Impact**: Reduced readability.
**Fix**: Extract to a helper function with clear name:
```python
def _looks_like_prompt_waiting(line: str) -> bool:
    return bool(line and line.strip().endswith((":?", "]")))
```

---

## Coverage

### Analyzed
- **Core**: `session.py`, `pty_manager.py`, `raw_buffer.py`, `cleaner.py`, `constants.py`
- **Daemon**: `manager.py`, `registry.py`, `pidfile.py`
- **API**: `server.py`, `models.py`
- **MCP**: `server.py`, `tools.py`
- **Stream**: `streaming_service.py`, `deduplicator.py`, `api_endpoints.py`, `config.py`
- **Utils**: `persistence.py`, `ports.py`, `shell_detect.py`, `names.py`
- **Config**: `config.py`
- **CLI**: `__main__.py`

### Not Analyzed
- **TUI**: `tui/app.py`, `tui/installer.py` — excluded per focus on core package
- **Tests**: Test files were not reviewed for correctness
- **Web UI**: Vue.js frontend code not reviewed
- **Build scripts**: `hatch_build.py`, `build.py`, `build_pyz.py`
- **Examples**: Example code in `examples/`

### Confidence
- **High** — Core session management, daemon, API, MCP tools reviewed in detail
- **Medium** — Stream functionality (less critical path)
- **Low** — TUI, web UI, build configuration

---

## Summary Statistics

| Severity | Count |
|----------|-------|
| CRITICAL | 6 |
| HIGH | 10 |
| MEDIUM | 10 |
| LOW | 7 |
| **Total** | **33** |

---

## Recommended Fix Priority

1. **CRITICAL-01, CRITICAL-02**: Timing attack on tokens — immediate security fix
2. **CRITICAL-03**: Rate limiting — prevents brute-force and DoS
3. **CRITICAL-05**: Memory leak — long-term stability
4. **HIGH-01, HIGH-02**: Exception swallowing — debuggability
5. **HIGH-09**: Newline handling bug — correctness

The remaining issues should be addressed in priority order during the next sprint.
