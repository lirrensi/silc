# Getting Started with SILC

Welcome to SILC! This guide will help you get up and running in 5 minutes.

---

## What You'll Learn

In this guide, you'll:
- ✅ Install SILC
- ✅ Start your first session
- ✅ Run commands via CLI
- ✅ Access the HTTP API
- ✅ Use the TUI interface
- ✅ Understand the basic concepts

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.12 or later** installed
  ```bash
  python --version  # Should show 3.12.x or higher
  ```

- **pip** (Python package manager)
  ```bash
  pip --version
  ```

- **One of these operating systems:**
  - Windows 10 or later
  - Linux (Ubuntu, Debian, Fedora, etc.)
  - macOS 10.15 or later

---

## Installation

### Option 1: Using pip (Recommended)

This installs SILC in your Python environment:

```bash
pip install -e .
```

**What this does:**
- Downloads SILC and its dependencies
- Installs the `silc` command globally
- Makes SILC available from anywhere in your terminal

**Verify installation:**
```bash
silc --version
```

You should see: `SILC v0.1.0`

---

### Option 2: Using pipx (Isolated Environment)

If you prefer to keep SILC isolated from your system Python:

```bash
pipx install git+https://github.com/lirrensi/silc.git
```

---

### Option 3: Standalone Installer (No pip Required)

**Windows:**
```cmd
install.bat
```

**Unix/Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

This downloads a pre-built binary and adds it to your PATH.

---

## Your First Session

### Step 1: Start the SILC Daemon

The daemon is the background process that manages sessions:

```bash
silc start
```

**Expected output:**
```
✓ SILC daemon started on port 19999
✓ Session created on port 20000
```

**What happened:**
- SILC started a daemon process on port 19999
- A new session was created on port 20000
- The session is ready to accept commands

---

### Step 2: Run Your First Command

Let's run a simple command in your session:

```bash
silc 20000 run "echo 'Hello from SILC!'"
```

**Expected output:**
```
Hello from SILC!
```

**What happened:**
- The CLI sent an HTTP request to the session
- The session executed the command in its shell
- The output was returned and displayed

---

### Step 3: View Session Output

You can view the output buffer at any time:

```bash
silc 20000 out
```

**Expected output:**
```
Hello from SILC!
```

---

### Step 4: Check Session Status

See what's happening in your session:

```bash
silc 20000 status
```

**Expected output:**
```json
{
  "alive": true,
  "idle_time": 5.2,
  "shell": "/bin/bash",
  "pid": 12345
}
```

---

### Step 5: Run Multiple Commands

You can chain commands using shell operators:

```bash
silc 20000 run "cd /tmp && ls && pwd"
```

**Expected output:**
```
[listing of /tmp directory]
/tmp
```

---

## Using the HTTP API

SILC's real power comes from its HTTP API. Let's try it:

### Get Session Status

```bash
curl http://localhost:20000/status
```

**Expected output:**
```json
{
  "alive": true,
  "idle_time": 10.5,
  "shell": "/bin/bash",
  "pid": 12345
}
```

### Run a Command via API

```bash
curl -X POST http://localhost:20000/run -d "date"
```

**Expected output:**
```json
{
  "output": "Tue Jan 27 12:00:00 UTC 2026",
  "exit_code": 0,
  "status": "success"
}
```

### Get Output via API

```bash
curl http://localhost:20000/out?lines=10
```

**Expected output:**
```json
{
  "output": "Last 10 lines of terminal output...",
  "lines": 10
}
```

---

## Using the TUI (Terminal User Interface)

SILC includes a beautiful native TUI for interactive sessions:

### Launch the TUI

```bash
silc 20000 tui
```

**What you'll see:**
- A full-screen terminal interface
- Real-time output display
- Interactive command input
- Session status information

**TUI Controls:**
- Type commands and press Enter to execute
- Use Ctrl+C to interrupt running commands
- Press `q` to quit the TUI

---

## Managing Multiple Sessions

SILC can run multiple sessions simultaneously:

### Create Another Session

```bash
silc create --port 20001
```

**Expected output:**
```
✓ Session created on port 20001
```

### List All Sessions

```bash
silc list
```

**Expected output:**
```
Active Sessions:
  Port 20000 - /bin/bash - Idle: 5.2s - Alive
  Port 20001 - /bin/bash - Idle: 2.1s - Alive
```

### Run Commands in Different Sessions

```bash
# Run in session 20000
silc 20000 run "echo 'Session 20000'"

# Run in session 20001
silc 20001 run "echo 'Session 20001'"
```

---

## Stopping SILC

When you're done, you can stop sessions and the daemon:

### Stop a Single Session

```bash
silc 20000 close
```

**Expected output:**
```
✓ Session 20000 closed
```

### Stop All Sessions and Daemon

```bash
silc shutdown
```

**Expected output:**
```
✓ All sessions closed
✓ Daemon stopped
```

### Force Kill Everything (Emergency)

```bash
silc killall
```

Use this only if SILC is unresponsive.

---

## Understanding SILC Concepts

### Daemon vs Session

- **Daemon**: The background process that manages sessions (port 19999)
- **Session**: An independent shell with its own PTY (ports 20000+)

Think of it like:
- Daemon = Restaurant manager
- Sessions = Individual tables

### Ports

- **19999**: Daemon port (management API)
- **20000-21000**: Session ports (default range)

### Output Buffer

Each session maintains an output buffer:
- Stores terminal output
- Configurable size (default: 5MB)
- Cleared with `silc <port> clear`

### API Tokens

For remote access, sessions use API tokens:
- Generated automatically per session
- Required for non-localhost connections
- Obtain via `curl http://localhost:20000/token`

---

## Common Workflows

### Workflow 1: Quick Command Execution

```bash
# Start and run
silc start
silc 20000 run "ls -la"
silc 20000 out
```

### Workflow 2: Long-Running Process

```bash
# Start session
silc start

# Run long process in background
silc 20000 run "nohup python long_task.py &"

# Monitor output
silc 20000 out
```

### Workflow 3: Interactive Development

```bash
# Start session
silc start

# Launch TUI for interactive work
silc 20000 tui
```

### Workflow 4: API Integration

```bash
# Start session
silc start

# Use from your application
curl -X POST http://localhost:20000/run -d "your command"
```

---

## Troubleshooting

### "Port already in use"

```bash
# Check what's using the port
lsof -i :19999  # Linux/macOS
netstat -ano | findstr :19999  # Windows

# Kill the process if needed
kill -9 <PID>  # Linux/macOS
taskkill /PID <PID> /F  # Windows
```

### "Daemon not starting"

```bash
# Check if daemon is already running
silc list

# Force kill everything
silc killall

# Try starting again
silc start
```

### "Session not responding"

```bash
# Check session status
silc 20000 status

# Interrupt if busy
silc 20000 interrupt

# Close if unresponsive
silc 20000 close
```

### "Import errors"

```bash
# Verify Python version
python --version  # Should be 3.12+

# Reinstall with dependencies
pip install -e .[test]

# Verify installation
pip list | grep silc
```

---

## Next Steps

Now that you've got SILC running, explore:

- 📖 [User Guide](user-guide.md) - Advanced usage
- 🔌 [API Reference](commands_and_api.md) - Complete API docs
- ⚙️ [Configuration](configuration.md) - Customize SILC
- 🎨 [Examples](../examples/) - Real-world use cases
- 🏗️ [Architecture](architecture.md) - How SILC works

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `silc start` | Start daemon and create session |
| `silc create` | Create new session |
| `silc <port> run "<cmd>"` | Execute command |
| `silc <port> out` | View output |
| `silc <port> status` | Check session status |
| `silc <port> tui` | Launch TUI |
| `silc list` | List all sessions |
| `silc shutdown` | Stop daemon |
| `silc killall` | Force kill everything |

---

## Need Help?

- 📖 [Documentation](../docs/)
- 💬 [GitHub Discussions](https://github.com/lirrensi/silc/discussions)
- 🐛 [Issue Tracker](https://github.com/lirrensi/silc/issues)

---

**Happy shell sharing! 🚀**