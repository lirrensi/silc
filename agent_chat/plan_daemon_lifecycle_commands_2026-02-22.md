# Plan: Daemon-Level Session Lifecycle Commands
_Move close/kill/restart to daemon API, add restart command, remove per-session lifecycle endpoints._

---

# Checklist
- [x] Step 1: Add daemon API endpoints (close, kill, restart)
- [x] Step 2: Remove per-session API endpoints (close, kill)
- [x] Step 3: Update CLI commands (close, kill, restart)
- [x] Step 4: Update web UI daemon API client
- [x] Step 5: Update web UI SessionView component
- [x] Step 6: Run linters and tests

---

## Context

Session lifecycle operations (close, kill, restart) need to move from per-session API (port 20000+) to daemon API (port 19999). This ensures operations work even when a session's HTTP server is unresponsive.

**Key files:**
- `silc/daemon/manager.py` — Daemon API endpoints, session management
- `silc/api/server.py` — Per-session FastAPI endpoints
- `silc/__main__.py` — CLI commands
- `manager_web_ui/src/lib/daemonApi.ts` — Web UI HTTP client
- `manager_web_ui/src/views/SessionView.vue` — Web UI session view

**Current state:**
- Daemon has `DELETE /sessions/{port}` for close
- Per-session API has `POST /close` and `POST /kill`
- No restart functionality exists
- CLI `close` and `kill` hit per-session API

**Target state:**
- Daemon has `POST /sessions/{port}/close`, `POST /sessions/{port}/kill`, `POST /sessions/{port}/restart`
- Per-session API has NO lifecycle endpoints
- CLI lifecycle commands hit daemon API
- Web UI lifecycle commands hit daemon API

## Prerequisites

- Python 3.11+ environment with `pip install -e .` completed
- Node.js 20+ for web UI build
- No running SILC daemon during changes

## Scope Boundaries

**DO NOT TOUCH:**
- `silc/core/session.py` — Session internals unchanged
- `silc/core/pty_manager.py` — PTY management unchanged
- `silc/daemon/registry.py` — Registry unchanged
- Tests in `tests/` — Will be updated separately if needed
- Any streaming, MCP, or TUI code

---

## Steps

### Step 1: Add daemon API endpoints (close, kill, restart)

Open `silc/daemon/manager.py`.

**1a. Replace DELETE endpoint with POST close:**

Find the `@app.delete("/sessions/{port}")` endpoint (approximately line 333). Replace the entire endpoint with:

```python
@app.post("/sessions/{port}/close")
async def close_session(port: int):
    """Gracefully close a session."""
    if port not in self.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    await self._ensure_cleanup_task(port)
    return {"status": "closed"}
```

**1b. Add kill endpoint after close endpoint:**

Add after the close endpoint:

```python
@app.post("/sessions/{port}/kill")
async def kill_session(port: int):
    """Force kill a session."""
    if port not in self.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = self.sessions.get(port)
    if session:
        try:
            await asyncio.wait_for(session.force_kill(), timeout=1.0)
        except asyncio.TimeoutError:
            write_daemon_log(f"Timeout force-killing session PTY: port={port}")
        except Exception as exc:
            write_daemon_log(f"Error force-killing session PTY: port={port}, error={exc}")

    await self._ensure_cleanup_task(port)
    return {"status": "killed"}
```

**1c. Add restart endpoint after kill endpoint:**

Add after the kill endpoint:

```python
@app.post("/sessions/{port}/restart")
async def restart_session(port: int):
    """Restart a session with the same port, name, cwd, and shell type."""
    if port not in self.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = self.sessions.get(port)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Capture session properties before cleanup
    name = session.name
    shell_info = session.shell_info
    cwd = session.cwd
    is_global = False

    # Check if session was global by checking the registry
    entry = self.registry.get(port)
    if entry:
        is_global = getattr(entry, 'is_global', False)

    # Get the socket before cleanup (we'll reuse it)
    session_socket = self._session_sockets.get(port)

    # Kill the old session but keep the socket
    try:
        await asyncio.wait_for(session.force_kill(), timeout=1.0)
    except asyncio.TimeoutError:
        write_daemon_log(f"Timeout force-killing session PTY during restart: port={port}")
    except Exception as exc:
        write_daemon_log(f"Error force-killing session PTY during restart: port={port}, error={exc}")

    # Remove from sessions dict but NOT from registry (we're keeping the identity)
    self.sessions.pop(port, None)

    # Cancel the old server task
    old_task = self._session_tasks.pop(port, None)
    if old_task:
        old_task.cancel()
        try:
            await asyncio.wait_for(old_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    # Remove old server
    self.servers.pop(port, None)

    # Create new session with same properties
    try:
        new_session = SilcSession(
            port,
            name,
            shell_info,
            cwd=cwd,
        )
        await new_session.start()

        self.sessions[port] = new_session

        # Update registry with new session_id
        self.registry.remove(port)
        self.registry.add(port, name, new_session.session_id, shell_info.type, is_global=is_global)

        # Update sessions.json
        from silc.utils.persistence import append_session_to_json
        from datetime import datetime
        append_session_to_json({
            "port": port,
            "name": name,
            "session_id": new_session.session_id,
            "shell": shell_info.type,
            "is_global": is_global,
            "cwd": cwd,
            "created_at": datetime.utcnow().isoformat() + "Z",
        })

        # Reuse existing socket or create new one
        if not session_socket:
            try:
                session_socket = self._reserve_session_socket(port, is_global)
            except OSError:
                # Port taken, find new one
                new_port = find_available_port(20000, 21000)
                session_socket = self._reserve_session_socket(new_port, is_global)
                port = new_port

        # Create new server
        server = self._create_session_server(new_session, is_global=is_global)
        self.servers[port] = server

        # Start server in background
        task = asyncio.create_task(server.serve(sockets=[session_socket]))
        self._session_tasks[port] = task
        self._attach_session_task(port, task)

        write_daemon_log(f"Session restarted: port={port}, name={name}")

        return {
            "status": "restarted",
            "port": port,
            "name": name,
            "shell": shell_info.type,
        }

    except Exception as exc:
        write_daemon_log(f"Error restarting session: port={port}, error={exc}")
        # Fallback: cleanup the broken state
        self._close_session_socket(port)
        self.sessions.pop(port, None)
        self.registry.remove(port)
        raise HTTPException(status_code=500, detail=f"Failed to restart session: {exc}")
```

**1d. Add imports if missing:**

At the top of the file, ensure `find_available_port` is imported from `silc.utils.ports`.

✅ Success: File `silc/daemon/manager.py` contains three new endpoints: `/sessions/{port}/close`, `/sessions/{port}/kill`, `/sessions/{port}/restart`. No `DELETE` endpoint exists for sessions.

❌ If failed: Check syntax errors. File must pass `python -m py_compile silc/daemon/manager.py`.

---

### Step 2: Remove per-session API endpoints (close, kill)

Open `silc/api/server.py`.

**2a. Find and remove the `/close` endpoint:**

Search for `@app.post("/close"`. Delete the entire endpoint function (typically 3-5 lines).

**2b. Find and remove the `/kill` endpoint:**

Search for `@app.post("/kill"`. Delete the entire endpoint function (typically 3-5 lines).

✅ Success: File `silc/api/server.py` no longer contains `/close` or `/kill` endpoints. The file passes `python -m py_compile silc/api/server.py`.

❌ If failed: Restore file from git: `git checkout silc/api/server.py`. Re-attempt step with care.

---

### Step 3: Update CLI commands (close, kill, restart)

Open `silc/__main__.py`.

**3a. Update `close` command:**

Find the `close` function (approximately line 730-756). Replace the entire function body with:

```python
@cli.port_subcommands.command()
@click.pass_context
def close(ctx: click.Context) -> None:
    """Gracefully close the session."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(_daemon_url(f"/sessions/{port}/close"), timeout=5)
        if resp.status_code == 404:
            click.echo(f"❌ Session on port {port} not found", err=True)
            return
        resp.raise_for_status()
        click.echo("✨ Session closed")
    except requests.RequestException:
        click.echo(f"❌ Failed to close session on port {port}", err=True)
```

**3b. Update `kill` command:**

Find the `kill` function (approximately line 760-771). Replace the entire function body with:

```python
@cli.port_subcommands.command()
@click.pass_context
def kill(ctx: click.Context) -> None:
    """Force kill the session."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(_daemon_url(f"/sessions/{port}/kill"), timeout=5)
        if resp.status_code == 404:
            click.echo(f"❌ Session on port {port} not found", err=True)
            return
        resp.raise_for_status()
        click.echo("💀 Session killed")
    except requests.RequestException:
        click.echo(f"❌ Failed to kill session on port {port}", err=True)
```

**3c. Add `restart` command after `kill`:**

Add the following new command after the `kill` function:

```python
@cli.port_subcommands.command()
@click.pass_context
def restart(ctx: click.Context) -> None:
    """Restart session with same port/name/cwd/shell."""
    port = ctx.parent.params["port"] if ctx.parent else 0
    try:
        resp = requests.post(_daemon_url(f"/sessions/{port}/restart"), timeout=10)
        if resp.status_code == 404:
            click.echo(f"❌ Session on port {port} not found", err=True)
            return
        resp.raise_for_status()
        data = resp.json()
        click.echo(f"🔄 Session restarted: {data['name']} on port {data['port']}")
    except requests.RequestException:
        click.echo(f"❌ Failed to restart session on port {port}", err=True)
```

✅ Success: File `silc/__main__.py` has updated `close`, `kill`, and new `restart` commands. All three call daemon API on port 19999. File passes `python -m py_compile silc/__main__.py`.

❌ If failed: Restore file from git: `git checkout silc/__main__.py`. Re-attempt step.

---

### Step 4: Update web UI daemon API client

Open `manager_web_ui/src/lib/daemonApi.ts`.

**4a. Update `closeSession` function:**

Find the `closeSession` function (approximately line 43-48). Replace with:

```typescript
export async function closeSession(port: number): Promise<void> {
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}/close`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to close session: HTTP ${resp.status}`)
  }
}
```

**4b. Add `killSession` function after `closeSession`:**

```typescript
export async function killSession(port: number): Promise<void> {
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}/kill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to kill session: HTTP ${resp.status}`)
  }
}
```

**4c. Add `restartSession` function after `killSession`:**

```typescript
export async function restartSession(port: number): Promise<void> {
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}/restart`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to restart session: HTTP ${resp.status}`)
  }
}
```

**4d. Update exports:**

Ensure the functions are exported. No changes needed if using `export async function` syntax.

✅ Success: File `manager_web_ui/src/lib/daemonApi.ts` has `closeSession`, `killSession`, and `restartSession` functions, all hitting daemon API.

❌ If failed: Check TypeScript syntax. Run `cd manager_web_ui && npx tsc --noEmit` to verify.

---

### Step 5: Update web UI SessionView component

Open `manager_web_ui/src/views/SessionView.vue`.

**5a. Update imports:**

Find the import line (approximately line 6). Replace with:

```typescript
import { closeSession, killSession, restartSession, sendSigterm, sendSigkill, sendInterrupt } from '@/lib/daemonApi'
```

**5b. Find and update `handleClose` function:**

Find the `handleClose` function. Replace with:

```typescript
async function handleClose(): Promise<void> {
  try {
    await closeSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to close session:', err)
  }
}
```

**5c. Find and update `handleKill` function:**

Find the `handleKill` function (may be named `handleSigkill` or similar). If it exists as a kill button handler, replace with:

```typescript
async function handleKill(): Promise<void> {
  try {
    await killSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to kill session:', err)
  }
}
```

**5d. Add `handleRestart` function:**

Add after `handleKill`:

```typescript
async function handleRestart(): Promise<void> {
  try {
    await restartSession(port.value)
    // Refresh the session connection
    manager.setWs(port.value, null)
    await manager.getSession(port.value)
  } catch (err) {
    console.error('Failed to restart session:', err)
  }
}
```

**5e. Update template to add restart button:**

Find the control bar section in the template. Add a restart button. Look for buttons like SIGINT, SIGTERM, SIGKILL. Add:

```vue
<button
  class="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm"
  @click="handleRestart"
  title="Restart session (same port/name/cwd/shell)"
>
  Restart
</button>
```

Place it between the signal buttons and the kill/close buttons.

**5f. Ensure signal handlers still call per-session API:**

Verify that `handleInterrupt`, `handleSigterm`, `handleSigkill` still call `sendInterrupt`, `sendSigterm`, `sendSigkill` (these hit per-session port).

✅ Success: File `manager_web_ui/src/views/SessionView.vue` has lifecycle handlers (close, kill, restart) calling daemon API, and signal handlers (interrupt, sigterm, sigkill) calling per-session API. Restart button exists in UI.

❌ If failed: Run `cd manager_web_ui && npx tsc --noEmit` to check TypeScript errors.

---

### Step 6: Run linters and tests

**6a. Run Python linters:**

```bash
pre-commit run --all-files
```

Expected: All checks pass. If failures exist, fix them.

**6b. Run Python type check:**

```bash
mypy silc/
```

Expected: No errors. If errors exist in changed files, fix them.

**6c. Build web UI:**

```bash
cd manager_web_ui && pnpm build
```

Expected: Build succeeds without errors.

**6d. Run Python tests:**

```bash
pytest tests/ -x
```

Expected: Tests pass. If tests fail related to changed endpoints, note the failures for separate fix.

✅ Success: All linters pass, web UI builds, tests pass.

❌ If failed: Report specific error output. Do not proceed to verification until passing.

---

## Verification

**Manual verification sequence:**

1. Start daemon: `silc start`
2. Create session: Note the port from output
3. Test close: `silc <port> close` — should print "✨ Session closed"
4. Start new session: `silc start`
5. Test kill: `silc <port> kill` — should print "💀 Session killed"
6. Start new session: `silc start`
7. Test restart: `silc <port> restart` — should print "🔄 Session restarted: <name> on port <port>"
8. Verify session still works after restart: `silc <port> run "echo hello"`
9. Open web UI: `silc manager`
10. Create session, test close/kill/restart buttons
11. Clean up: `silc shutdown`

**API verification:**

```bash
# Start daemon and session
silc start
# Note the port, then:

# Test close
curl -X POST http://127.0.0.1:19999/sessions/20000/close
# Expected: {"status": "closed"}

# Start new session, then test kill
curl -X POST http://127.0.0.1:19999/sessions/20000/kill
# Expected: {"status": "killed"}

# Start new session, then test restart
curl -X POST http://127.0.0.1:19999/sessions/20000/restart
# Expected: {"status": "restarted", "port": 20000, "name": "...", "shell": "..."}
```

## Rollback

If critical failure occurs:

```bash
# Restore all changed files
git checkout silc/daemon/manager.py
git checkout silc/api/server.py
git checkout silc/__main__.py
git checkout manager_web_ui/src/lib/daemonApi.ts
git checkout manager_web_ui/src/views/SessionView.vue

# Rebuild web UI
cd manager_web_ui && pnpm build
```
