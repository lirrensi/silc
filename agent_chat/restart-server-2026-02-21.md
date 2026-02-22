# Plan: Add `silc restart-server` Command
_Add ability to restart the daemon HTTP server without killing PTY sessions._

---

# Checklist
- [x] Step 1: Add `_restart_event` field to `SilcDaemon` class
- [x] Step 2: Add `POST /restart-server` endpoint to daemon API
- [x] Step 3: Add `_watch_restart` background task
- [x] Step 4: Add `silc restart-server` CLI command
- [x] Step 5: Update documentation

---

## Context

The daemon runs a uvicorn server that handles HTTP requests. Currently, there's no way to restart this HTTP layer without killing all PTY sessions. This plan adds a `restart-server` feature that stops and restarts the uvicorn server while keeping all sessions alive.

**Key files:**
- `silc/daemon/manager.py` — `SilcDaemon` class and daemon API endpoints
- `silc/__main__.py` — CLI commands

**Current daemon structure (relevant parts):**
- `SilcDaemon._daemon_server` — uvicorn.Server instance for daemon API (port 19999)
- `SilcDaemon.sessions` — Dict[int, SilcSession] — survives server restart
- `SilcDaemon._shutdown_event` — asyncio.Event for shutdown signaling

---

## Prerequisites

- Python environment with SILC installed (`pip install -e .`)
- Daemon is running OR can be started

---

## Scope Boundaries

**OUT OF SCOPE:**
- Session PTY management — do not touch `SilcSession` or `pty_manager.py`
- Per-session servers (ports 20000+) — these continue running during daemon server restart
- Any changes to shutdown/killall behavior

---

## Steps

### Step 1: Add `_restart_event` field to `SilcDaemon` class

Open `silc/daemon/manager.py`. Find the `SilcDaemon.__init__` method (approximately line 70-87). Add a new event field alongside `_shutdown_event`.

In `__init__`, after the line:
```python
self._shutdown_event = asyncio.Event()
```
Add:
```python
self._restart_event = asyncio.Event()
```

✅ Success: `self._restart_event` exists as an `asyncio.Event()` in `SilcDaemon.__init__`
❌ If failed: Verify you're editing `silc/daemon/manager.py`, not another file. The line must be inside `__init__` method.

---

### Step 2: Add `POST /restart-server` endpoint to daemon API

Open `silc/daemon/manager.py`. Find the `_create_daemon_api` method (approximately line 89-339). Inside this method, after the `@app.post("/killall")` endpoint definition (approximately line 296-337), add a new endpoint.

Add the following code after the `killall` endpoint:

```python
        @app.post("/restart-server")
        async def restart_server():
            """Restart the HTTP server without killing sessions."""
            write_daemon_log("Server restart requested")
            self._restart_event.set()
            return {"status": "restarting"}
```

✅ Success: A new `POST /restart-server` endpoint exists in the daemon API that sets `_restart_event` and returns `{"status": "restarting"}`
❌ If failed: Check that the endpoint is inside `_create_daemon_api` method, indented correctly (part of the FastAPI app routes).

---

### Step 3: Add `_watch_restart` background task

Open `silc/daemon/manager.py`. Add a new async method `_watch_restart` to the `SilcDaemon` class.

Find the `_watch_shutdown` method (approximately line 565-594). After this method, add the new `_watch_restart` method:

```python
    async def _watch_restart(self) -> None:
        """Watch for restart requests and restart the HTTP server."""
        while self._running and not self._shutdown_event.is_set():
            await self._restart_event.wait()
            if self._shutdown_event.is_set():
                return

            write_daemon_log("Restarting HTTP server...")

            # Stop current server
            if self._daemon_server:
                self._daemon_server.should_exit = True
                # Give it time to drain connections
                await asyncio.sleep(0.5)

            # Recreate and restart
            self._daemon_api_app = self._create_daemon_api()
            config = uvicorn.Config(
                self._daemon_api_app,
                host="127.0.0.1",
                port=DAEMON_PORT,
                log_level="info",
                access_log=True,
            )
            self._daemon_server = uvicorn.Server(config)

            # Clear the restart event before serving
            self._restart_event.clear()

            # Start serving in a new task (we're in a background task)
            asyncio.create_task(self._daemon_server.serve())

            write_daemon_log("HTTP server restarted")

            # Small delay to prevent tight restart loops
            await asyncio.sleep(0.1)
```

Now find the `start` method (approximately line 628-687). Find the section that starts background tasks (approximately line 675-676):

```python
        gc_task = asyncio.create_task(self._garbage_collect())
        shutdown_watcher = asyncio.create_task(self._watch_shutdown())
```

Add a restart watcher task:

```python
        gc_task = asyncio.create_task(self._garbage_collect())
        shutdown_watcher = asyncio.create_task(self._watch_shutdown())
        restart_watcher = asyncio.create_task(self._watch_restart())
```

And in the `finally` block (approximately line 682-687), add cancellation for the restart watcher:

```python
        finally:
            # Cleanup on exit
            gc_task.cancel()
            shutdown_watcher.cancel()
            restart_watcher.cancel()
            remove_pidfile()
            write_daemon_log("Silc daemon stopped")
            self._running = False
```

✅ Success: `_watch_restart` method exists, is started as a background task in `start()`, and is cancelled in the finally block
❌ If failed: Verify method indentation matches other methods. Check that all three task creations and cancellations are present.

---

### Step 4: Add `silc restart-server` CLI command

Open `silc/__main__.py`. Find the `killall` command definition (approximately line 742-754). After this command, add the new `restart-server` command:

```python
@cli.command(name="restart-server")
def restart_server() -> None:
    """Restart the daemon HTTP server (sessions survive)."""
    try:
        resp = requests.post(_daemon_url("/restart-server"), timeout=5)
        resp.raise_for_status()
        click.echo("✨ Daemon HTTP server restarted (sessions preserved)")
    except requests.RequestException as e:
        click.echo(f"❌ Failed to restart server: {e}", err=True)
```

✅ Success: `silc restart-server` command exists and makes POST request to `/restart-server` endpoint
❌ If failed: Verify the decorator is `@cli.command(name="restart-server")` and function is at module level, not nested.

---

### Step 5: Update documentation

Open `docs/product.md`. Find the "Daemon Management" commands table (approximately line 145-152). Add a new row after the `shutdown` row:

```markdown
| `silc restart-server` | Restart daemon HTTP server (sessions survive) |
```

Open `docs/arch_cli.md`. Find the command structure tree (approximately line 62-90). Add `restart-server` in the appropriate place after `killall`:

```markdown
├── restart-server
```

Find the Daemon Commands section (approximately line 123-180). After the `killall` description, add:

```markdown
### `silc restart-server`

```python
@cli.command(name="restart-server")
def restart_server():
    requests.post("http://127.0.0.1:19999/restart-server", timeout=5)
```

Restarts the daemon HTTP server without killing PTY sessions. Useful for applying configuration changes or recovering from server issues while keeping shells alive.
```

Open `docs/arch_daemon.md`. Find the Daemon API Endpoints table (approximately line 144-151). Add a new row:

```markdown
| `POST` | `/restart-server` | Restart HTTP server without killing sessions |
```

After the `/killall` endpoint description (approximately line 396), add the new endpoint documentation:

```markdown
### `POST /restart-server`

**Response:**
```json
{
  "status": "restarting"
}
```

Restarts the HTTP server layer while keeping all PTY sessions alive. The daemon process continues running; only the uvicorn server is stopped and restarted.

**Use case:** Recovering from HTTP issues or applying server-level changes without losing shell sessions.
```

✅ Success: All three documentation files updated with `restart-server` information
❌ If failed: Check each file individually. Ensure markdown tables and code blocks are properly formatted.

---

## Verification

1. Start the daemon: `silc start`
2. Create a session and run a command: `silc 20000 run "echo hello"`
3. Verify session exists: `silc list`
4. Run restart: `silc restart-server`
5. Verify sessions still exist: `silc list` (should show same session)
6. Verify session still works: `silc 20000 run "echo world"` (should show previous output preserved)

**Expected output after restart:**
- `silc list` shows same session(s)
- `silc 20000 out` shows preserved terminal history
- Commands still execute in the session

---

## Rollback

If critical failure occurs:

1. Remove the `restart-server` CLI command from `silc/__main__.py`
2. Remove the `/restart-server` endpoint from `silc/daemon/manager.py`
3. Remove the `_watch_restart` method and its task from `silc/daemon/manager.py`
4. Remove the `_restart_event` field from `SilcDaemon.__init__`
5. Revert documentation changes

```bash
git checkout -- silc/daemon/manager.py silc/__main__.py docs/product.md docs/arch_cli.md docs/arch_daemon.md
```
