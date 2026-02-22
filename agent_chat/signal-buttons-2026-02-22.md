# Plan: Signal Buttons for Manager Web UI
_Add SIGTERM/SIGKILL endpoints and control bar buttons; fix Ctrl+V context menu issue._

---

# Checklist
- [x] Step 1: Add signal methods to PTYBase abstract class
- [x] Step 2: Implement signal methods in UnixPTY
- [x] Step 3: Implement signal methods in WindowsPTY
- [x] Step 4: Implement signal methods in StubPTY
- [x] Step 5: Add signal methods to SilcSession
- [x] Step 6: Add /sigterm and /sigkill API endpoints
- [x] Step 7: Add API helper functions in daemonApi.ts
- [x] Step 8: Update control bar buttons in SessionView.vue
- [x] Step 9: Fix Ctrl+V context menu issue in terminalManager.ts
- [x] Step 10: Verify backend with manual test
- [x] Step 11: Build and verify frontend

---

## Context
The Manager Web UI (`manager_web_ui/`) needs control bar buttons for sending signals to processes. The backend currently has `/interrupt` (Ctrl+C) and `/kill` (destroy session), but lacks `/sigterm` and `/sigkill` for terminating foreground processes while keeping the session alive.

**Key files:**
- `silc/core/pty_manager.py` — PTY abstraction with UnixPTY, WindowsPTY, StubPTY
- `silc/core/session.py` — SilcSession class
- `silc/api/server.py` — FastAPI endpoints
- `manager_web_ui/src/views/SessionView.vue` — Control bar UI
- `manager_web_ui/src/stores/terminalManager.ts` — Terminal/WebSocket handling
- `manager_web_ui/src/lib/daemonApi.ts` — API helper functions

**Existing bugs to fix:**
- Ctrl+C/Ctrl+D buttons in SessionView.vue write directly to xterm.js instead of sending through WebSocket
- Ctrl+V triggers browser's native paste context menu, defocusing the terminal

## Prerequisites
- Python 3.11+ environment with `pip install -e .` completed
- Node.js 18+ environment with `npm install` in `manager_web_ui/` completed
- `psutil` package installed (already a dependency)

## Scope Boundaries
- Do NOT modify `docs/` (already updated)
- Do NOT modify `static/web/index.html` (standalone web UI, not manager)
- Do NOT modify CLI commands in `silc/__main__.py`

---

## Steps

### Step 1: Add signal methods to PTYBase abstract class

Open `silc/core/pty_manager.py`. Find the `PTYBase` class (starts around line 16). After the `is_alive` abstract method, add two new abstract methods:

```python
@abstractmethod
def send_sigterm(self) -> None:
    """Send SIGTERM to foreground process group (graceful)."""
    ...

@abstractmethod
def send_sigkill(self) -> None:
    """Send SIGKILL to foreground process group (force)."""
    ...
```

Add these after the `is_alive` method definition (around line 41), before the `StubPTY` class.

✅ Success: `PTYBase` class has two new abstract methods: `send_sigterm` and `send_sigkill`.
❌ If failed: Ensure exact indentation matches other abstract methods (4 spaces before `@abstractmethod`).

---

### Step 2: Implement signal methods in UnixPTY

Open `silc/core/pty_manager.py`. Find the `UnixPTY` class (starts around line 68). After the `is_alive` method (around line 148), add:

```python
def send_sigterm(self) -> None:
    """Send SIGTERM to the foreground process group."""
    if self.pid:
        try:
            import os
            import signal
            os.killpg(os.getpgid(self.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass

def send_sigkill(self) -> None:
    """Send SIGKILL to the foreground process group."""
    if self.pid:
        try:
            import os
            import signal
            os.killpg(os.getpgid(self.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            pass
```

✅ Success: `UnixPTY` class has `send_sigterm` and `send_sigkill` methods.
❌ If failed: Check indentation is 4 spaces, methods are inside the `UnixPTY` class.

---

### Step 3: Implement signal methods in WindowsPTY

Open `silc/core/pty_manager.py`. Find the `WindowsPTY` class (starts around line 151). After the `is_alive` method (around line 300), before `_read_sync`, add:

```python
def send_sigterm(self) -> None:
    """Gracefully terminate child processes (Windows has no SIGTERM)."""
    import psutil
    if self.pid:
        try:
            proc = psutil.Process(self.pid)
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass

def send_sigkill(self) -> None:
    """Forcefully kill child processes."""
    import psutil
    if self.pid:
        try:
            proc = psutil.Process(self.pid)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass
```

✅ Success: `WindowsPTY` class has `send_sigterm` and `send_sigkill` methods.
❌ If failed: Check indentation is 4 spaces, methods are inside the `WindowsPTY` class.

---

### Step 4: Implement signal methods in StubPTY

Open `silc/core/pty_manager.py`. Find the `StubPTY` class (starts around line 43). After the `is_alive` method (around line 65), add:

```python
def send_sigterm(self) -> None:
    """No-op for stub PTY."""
    return None

def send_sigkill(self) -> None:
    """No-op for stub PTY."""
    return None
```

✅ Success: `StubPTY` class has `send_sigterm` and `send_sigkill` methods that return None.
❌ If failed: Check indentation is 4 spaces, methods are inside the `StubPTY` class.

---

### Step 5: Add signal methods to SilcSession

Open `silc/core/session.py`. Find the `interrupt` method (around line 427). After the `interrupt` method, before `clear_buffer`, add:

```python
async def send_sigterm(self) -> None:
    """Send SIGTERM to the foreground process group."""
    self.pty.send_sigterm()

async def send_sigkill(self) -> None:
    """Send SIGKILL to the foreground process group."""
    self.pty.send_sigkill()
```

✅ Success: `SilcSession` class has `send_sigterm` and `send_sigkill` async methods.
❌ If failed: Check indentation is 4 spaces, methods are inside the `SilcSession` class.

---

### Step 6: Add /sigterm and /sigkill API endpoints

Open `silc/api/server.py`. Find the `/interrupt` endpoint (around line 183). After the `/interrupt` endpoint, before `/clear`, add:

```python
@app.post("/sigterm", dependencies=[Depends(_require_token)])
async def sigterm() -> dict:
    _check_alive()
    await session.send_sigterm()
    return {"status": "sigterm_sent"}

@app.post("/sigkill", dependencies=[Depends(_require_token)])
async def sigkill() -> dict:
    _check_alive()
    await session.send_sigkill()
    return {"status": "sigkill_sent"}
```

✅ Success: Two new POST endpoints `/sigterm` and `/sigkill` exist in server.py.
❌ If failed: Ensure endpoints are inside the `create_app` function, after `/interrupt` endpoint.

---

### Step 7: Add API helper functions in daemonApi.ts

Open `manager_web_ui/src/lib/daemonApi.ts`. After the `resizeSession` function (around line 55), add:

```typescript
export async function sendSigterm(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/sigterm`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGTERM: HTTP ${resp.status}`)
  }
}

export async function sendSigkill(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/sigkill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGKILL: HTTP ${resp.status}`)
  }
}

export async function sendInterrupt(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/interrupt`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send interrupt: HTTP ${resp.status}`)
  }
}
```

✅ Success: Three new exported functions in daemonApi.ts: `sendSigterm`, `sendSigkill`, `sendInterrupt`.
❌ If failed: Check TypeScript syntax, ensure functions are at module level (not inside another function).

---

### Step 8: Update control bar buttons in SessionView.vue

Open `manager_web_ui/src/views/SessionView.vue`.

**8a. Add imports at the top of `<script setup>`:**

Find line 6: `import { closeSession } from '@/lib/daemonApi'`

Replace with:
```typescript
import { closeSession, sendSigterm, sendSigkill, sendInterrupt } from '@/lib/daemonApi'
```

**8b. Add helper function to send via WebSocket:**

After the `handleKill` function (around line 65), before `</script>`, add:

```typescript
function sendViaWs(text: string): void {
  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN) {
    s.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
  }
}

async function handleInterrupt(): Promise<void> {
  await sendInterrupt(port.value)
}

async function handleSigterm(): Promise<void> {
  await sendSigterm(port.value)
}

async function handleSigkill(): Promise<void> {
  await sendSigkill(port.value)
}

function handlePaste(): void {
  navigator.clipboard.readText().then(text => {
    sendViaWs(text)
  }).catch(() => {
    // Clipboard access denied
  })
}

function scrollToBottom(): void {
  const s = manager.getSession(port.value)
  if (s?.terminal) {
    s.terminal.scrollToBottom()
  }
}
```

**8c. Replace the control bar template:**

Find the `<div class="control-bar ...">` section (around line 113). Replace the entire control-bar div with:

```html
<!-- Control Bar -->
<div class="control-bar flex items-center gap-2 px-4 py-2 bg-[#252526] border-t border-[#5e5e62]">
  <button
    @click="handleInterrupt"
    class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    title="SIGINT (Ctrl+C) - Interrupt current process"
  >
    SIGINT
  </button>
  <button
    @click="handleSigterm"
    class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    title="SIGTERM - Graceful termination"
  >
    SIGTERM
  </button>
  <button
    @click="handleSigkill"
    class="px-3 py-1 text-sm bg-[#f87171]/20 hover:bg-[#f87171]/40 border border-[#f87171]/50 text-[#f87171] rounded transition-colors"
    title="SIGKILL - Force kill (nuclear option)"
  >
    SIGKILL
  </button>
  <button
    @click="handleClear"
    class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
  >
    Clear
  </button>
  <div class="w-px h-6 bg-[#5e5e62] mx-1"></div>
  <button
    @click="handlePaste"
    class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    title="Paste from clipboard"
  >
    Paste
  </button>
  <button
    @click="scrollToBottom"
    class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    title="Scroll to bottom"
  >
    ↓ Bottom
  </button>
  <div class="flex gap-1 ml-2">
    <button
      @click="sendViaWs('\x1b[A')"
      class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    >
      ↑
    </button>
    <button
      @click="sendViaWs('\x1b[D')"
      class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    >
      ←
    </button>
    <button
      @click="sendViaWs('\x1b[B')"
      class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    >
      ↓
    </button>
    <button
      @click="sendViaWs('\x1b[C')"
      class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
    >
      →
    </button>
  </div>
</div>
```

✅ Success: SessionView.vue has new control bar with SIGINT, SIGTERM, SIGKILL, Clear, Paste, Scroll to Bottom buttons. Arrow keys use WebSocket.
❌ If failed: Check for TypeScript errors, ensure all functions are defined before used in template.

---

### Step 9: Fix Ctrl+V to paste directly to terminal (no browser interference)

Open `manager_web_ui/src/stores/terminalManager.ts`.

**The problem:** Browser intercepts Ctrl+V before xterm can handle it, showing paste dialog.

**The solution:** Handle Ctrl+V in `attachCustomKeyEventHandler` which runs FIRST. Return `false` to prevent xterm/browser from processing the key.

**9a. Find the `attachCustomKeyEventHandler` call (around line 73):**

Replace the entire handler with this:

```typescript
// Handle special keys BEFORE xterm processes them
terminal.attachCustomKeyEventHandler((event) => {
  if (event.type !== 'keydown') return true

  // Ctrl+Enter
  if (event.ctrlKey && event.key === 'Enter') {
    if (session.ws && session.ws.readyState === WebSocket.OPEN) {
      session.ws.send(JSON.stringify({ event: 'type', text: '\x1b[13;5u', nonewline: true }))
    }
    return false
  }

  // Shift+Enter
  if (event.shiftKey && event.key === 'Enter' && !event.ctrlKey) {
    if (session.ws && session.ws.readyState === WebSocket.OPEN) {
      session.ws.send(JSON.stringify({ event: 'type', text: '\x1b[13;2u', nonewline: true }))
    }
    return false
  }

  // Ctrl+V - paste clipboard directly to terminal via WebSocket
  // Return false to prevent xterm AND browser from doing anything
  if (event.ctrlKey && event.key === 'v' && !event.shiftKey && !event.altKey) {
    navigator.clipboard.readText().then(text => {
      if (session.ws && session.ws.readyState === WebSocket.OPEN) {
        session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
      }
    }).catch(() => {
      // Clipboard access denied - ignore silently
    })
    return false // CRITICAL: stops xterm + browser from handling this
  }

  return true
})
```

**9b. Remove the duplicate Ctrl+V handling from DOM keydown handler:**

Find `keydownHandler` inside `setupBrowserEventHandlers` (around line 218). Remove the Ctrl+V block (lines 231-242). The handler should only handle Ctrl+C:

```typescript
const keydownHandler = (e: KeyboardEvent) => {
  if (!e.ctrlKey) return

  // Ctrl+C with selection - copy to clipboard
  if (e.code === 'KeyC' && session.terminal.hasSelection()) {
    e.preventDefault()
    e.stopPropagation()
    navigator.clipboard.writeText(session.terminal.getSelection())
    session.terminal.clearSelection()
    return
  }
}
```

✅ Success: Press Ctrl+V → clipboard text is sent to terminal via WebSocket → no browser dialog, no context menu, works like native terminal.
❌ If failed: Verify `return false` is present after Ctrl+V handling. Check browser console for errors.

---

### Step 10: Verify backend with manual test

Run the following commands in terminal:

```bash
cd C:\Users\rx\001_Code\100_M\SILC
pip install -e .
silc start
```

Then test the new endpoints:

```bash
# Get the session port (likely 20000)
silc list

# Test /sigterm endpoint
curl -X POST http://127.0.0.1:20000/sigterm

# Test /sigkill endpoint
curl -X POST http://127.0.0.1:20000/sigkill
```

✅ Success: Both endpoints return `{"status": "sigterm_sent"}` and `{"status": "sigkill_sent"}` respectively. No errors in terminal.
❌ If failed: Check server logs with `silc logs`. Verify session is running with `silc list`.

---

### Step 11: Build and verify frontend

Run the following commands:

```bash
cd C:\Users\rx\001_Code\100_M\SILC\manager_web_ui
npm run build
```

Then copy the build output:

```bash
# On Windows
xcopy /E /Y dist\* ..\static\manager\
```

Start the manager UI:

```bash
cd C:\Users\rx\001_Code\100_M\SILC
silc manager
```

In the browser:
1. Open a session
2. Run a long command like `sleep 100`
3. Click SIGINT - process should be interrupted
4. Run `sleep 100` again
5. Click SIGTERM - process should terminate gracefully
6. Run `sleep 100` again
7. Click SIGKILL - process should be killed immediately
8. Test Paste button with text in clipboard
9. Test Scroll to Bottom with lots of output
10. Test that Ctrl+V no longer shows browser paste context menu

✅ Success: All buttons work as expected. Ctrl+V does not show browser paste dialog.
❌ If failed: Check browser console for errors. Check network tab for failed requests.

---

## Verification

1. Backend: `curl -X POST http://127.0.0.1:20000/sigterm` returns `{"status": "sigterm_sent"}`
2. Backend: `curl -X POST http://127.0.0.1:20000/sigkill` returns `{"status": "sigkill_sent"}`
3. Frontend: Manager UI shows 6 control buttons: SIGINT, SIGTERM, SIGKILL, Clear, Paste, ↓ Bottom
4. Frontend: SIGINT button interrupts running process
5. Frontend: SIGTERM button terminates running process gracefully
6. Frontend: SIGKILL button kills running process forcefully
7. Frontend: Paste button sends clipboard content to terminal
8. Frontend: Scroll to Bottom button scrolls terminal to bottom
9. Frontend: Ctrl+V does NOT show browser paste context menu
10. Session remains alive after SIGINT/SIGTERM/SIGKILL (only `/kill` destroys session)

## Rollback

If critical failure occurs:

1. Discard all Python changes:
   ```bash
   git checkout -- silc/core/pty_manager.py silc/core/session.py silc/api/server.py
   ```

2. Discard all frontend changes:
   ```bash
   git checkout -- manager_web_ui/src/
   ```

3. Reinstall:
   ```bash
   pip install -e .
   cd manager_web_ui && npm run build
   ```

4. Report which step failed and the error message.
