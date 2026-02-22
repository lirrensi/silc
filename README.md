# SILC - SharedInteractiveLinkedCmd
(bruh)

[![PyPI version](https://badge.fury.io/py/silc.svg)](https://badge.fury.io/py/silc)
[![Python Version](https://img.shields.io/pypi/pyversions/silc.svg)](https://pypi.org/project/silc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://github.com/lirrensi/silc/workflows/CI/badge.svg)](https://github.com/lirrensi/silc/actions)

**Your terminal, unified.** A manageable VI (Virtual Interface) for your shells — where humans and AI agents collaborate in real-time, with full visibility and control.

---

## 🎯 The Problem

Most AI coding agents (Claude, GPT-4, Cursor, etc.) spawn isolated shells with no access to your environment:

- ❌ **No access to your tools** - Can't see your aliases, config, or installed programs
- ❌ **No context continuity** - Each command runs in a fresh, isolated environment
- ❌ **Can't use TUI apps** - vim, htop, git interactive don't work
- ❌ **No visibility** - You can't see what they're doing or intervene
- ❌ **No collaboration** - You and the agent can't work together
- ❌ **No unified interface** - Juggling between terminals, logs, and monitoring tools

## ✨ The SILC Solution

SILC v3 is a **manageable VI** — a single place to work with your terminals, share them, and control them via REST API, WebSocket, TUI, or Web UI.

- ✅ **Full environment access** - Agents work in your actual shell with all your tools
- ✅ **Real-time visibility** - See exactly what agents are doing as it happens
- ✅ **Interactive TUI support** - Agents can use vim, htop, git, and any terminal app
- ✅ **Human-in-the-loop** - Monitor, interrupt, or take over at any moment
- ✅ **True collaboration** - Work side-by-side with AI agents in the same session
- ✅ **Unified interface** - One VI for all terminals: CLI, TUI, Web UI, REST API, WebSocket, MCP

## 🚀 Quick Start

```bash
# Install
pip install -e .

# Start the daemon and create a session
silc start

# Run commands that complete (you or agent)
silc 20000 run "git status"
silc 20000 run "npm test"
silc 20000 run "ls -la"

# View output in real-time
silc 20000 out
```

**That's it!** Your AI agent can now work in YOUR shell environment.

---

## 🔑 Key Concepts

### `run` vs `in` — Critical Distinction

| Command | What it does | Works with | DOES NOT work with |
|---------|--------------|------------|-------------------|
| **`run`** | Waits for command to **finish** and return to shell prompt | `git status`, `npm test`, `ls`, `cat file.txt`, scripts | ❌ vim, htop, SSH, REPLs, any TUI/interactive app |
| **`in`** | Sends input **immediately**, no waiting | ✅ vim, htop, SSH, REPLs, any interactive app | N/A (works with everything) |

**`run` uses sentinel detection** — it injects markers and waits for the shell to return to prompt. If the command doesn't return (like vim), `run` will hang until timeout.

**`in` is fire-and-forget** — it sends text to the PTY immediately and returns. Use this for interactive apps.

**Examples:**
```bash
# ═══════════════════════════════════════════════════════════
# RUN - only for commands that COMPLETE
# ═══════════════════════════════════════════════════════════

silc 20000 run "git status"        # ✅ Runs, finishes, returns output
silc 20000 run "npm test"          # ✅ Runs tests, finishes, returns results
silc 20000 run "ls -la"            # ✅ Lists files, finishes, returns output
silc 20000 run "cat config.json"   # ✅ Prints file, finishes, returns content
silc 20000 run "./build.sh"        # ✅ Runs script, finishes, returns output

# ═══════════════════════════════════════════════════════════
# IN - for EVERYTHING else (interactive apps)
# ═══════════════════════════════════════════════════════════

silc 20000 in "vim config.py"      # ✅ Opens vim (doesn't wait)
silc 20000 in "htop"               # ✅ Opens htop (doesn't wait)
silc 20000 in "ssh user@server"    # ✅ Opens SSH session (doesn't wait)
silc 20000 in "python"             # ✅ Opens Python REPL (doesn't wait)
silc 20000 in "docker run -it ubuntu bash"  # ✅ Opens container shell (doesn't wait)

# Then read output to see what's happening
silc 20000 out                     # View current terminal state

# Send keystrokes to control the app
silc 20000 in "i"                  # Enter insert mode in vim
silc 20000 in "hello world"        # Type text
silc 20000 in "\x1b"               # Press Escape
silc 20000 in ":wq\n"              # Save and quit vim
```

**⚠️ Common Mistakes:**
```bash
# ❌ WRONG - will hang until timeout!
silc 20000 run "vim config.py"

# ✅ CORRECT - use 'in' for interactive apps
silc 20000 in "vim config.py"
```

### Named Sessions — Like Docker Containers

Name your sessions for easier management:

```bash
# Create named session
silc start my-project              # Name: "my-project"
silc start dev-server --port 20001 # Name: "dev-server"

# Auto-generated names (if you don't specify)
silc start                         # Name: "happy-fox-42" (random: adjective-noun-number)

# Use names instead of ports
silc my-project run "git status"   # Instead of: silc 20000 run ...
silc dev-server out                # Instead of: silc 20001 out

# List sessions to see names
silc list
# Output:
#   20000 | my-project       | abc12345 | bash   | idle:   5s ✓
#   20001 | dev-server       | def67890 | zsh    | idle:  12s ✓
```

**Name format rules:**
- ✅ Must start with lowercase letter: `[a-z]`
- ✅ Can contain: lowercase letters, numbers, hyphens
- ❌ Cannot end with hyphen
- ✅ Examples: `my-project`, `dev-server-1`, `test123`
- ❌ Examples: `My-Project` (uppercase), `123test` (starts with number), `test-` (ends with hyphen)

### Persistence — Sessions Survive Restarts

Sessions are persisted to `~/.silc/sessions.json` and can be resurrected:

```bash
# Do work
silc start my-project
silc my-project run "git status"

# Shutdown (saves session metadata)
silc shutdown

# Later... resurrect sessions
silc resurrect
# Output: ✨ Restored 1 session(s):
#            my-project → port 20000

# Continue work
silc my-project run "git status"
```

**What persists:** port, name, shell, working directory
**What doesn't persist:** running commands, buffer content, process state

---

## 💡 How It Works

SILC transforms your terminal into a **manageable VI** with multiple interfaces:

```bash
# Start SILC daemon (manages all sessions)
silc start

# Create a session (named or auto-named)
silc start my-session --port 20000

# Run commands in your actual shell (commands that complete)
silc 20000 run "npm test"
silc 20000 run "python -m pytest"

# Or interact with TUI apps (fire-and-forget)
silc 20000 in "vim main.py"

# Watch what happens
silc 20000 out
```

**The CLI is the primary interface** — simple for humans, perfect for agents. But SILC v3 offers so much more:

| Interface | Use Case |
|-----------|----------|
| **CLI** | Quick commands, agent integration |
| **TUI** | Native terminal UI (Rust-based, blazing fast) |
| **Web UI** | Browser-based terminal management |
| **REST API** | Programmatic control, automation |
| **WebSocket** | Real-time streaming, live output |
| **MCP Server** | AI agent integration (Claude Code, Cursor) |

---

## 🎨 Use Cases

### 1. **AI Agent Works in Your Environment**

```bash
# Agent uses your tools, config, and aliases
silc 20000 run "git status"      # Your git config
silc 20000 run "npm test"        # Your npm/node
silc 20000 run "my-alias"        # Your .bashrc aliases
```

### 2. **Collaborative Debugging**

```bash
# You run tests
silc 20000 run "pytest tests/"

# Agent investigates in YOUR environment
silc 20000 run "cat logs/error.log"
silc 20000 in "vim tests/test_api.py"  # Interactive: use 'in'

# Agent suggests fix, you apply it
```

### 3. **Monitor Long-Running Processes**

```bash
# Start a task in background
silc 20000 in "nohup python train.py > train.log 2>&1 &"

# Monitor the log
silc 20000 run "tail -20 train.log"
```

### 4. **Agent Uses TUI Apps**

```bash
# For interactive apps, ALWAYS use 'in' (fire-and-forget)
silc 20000 in "vim config.json"
silc 20000 in "htop"
silc 20000 in "git rebase -i HEAD~3"
silc 20000 in "docker run -it ubuntu bash"

# Then read the screen to see what's happening
silc 20000 out

# Send keystrokes to control
silc 20000 in "q"                 # Quit htop
silc 20000 in ":wq\n"             # Save and quit vim
```

### 5. **Remote Server Management**

```bash
# SSH into server
ssh user@production-server

# Start SILC
silc start

# Agent deploys and monitors
silc 20000 run "./deploy.sh"
silc 20000 in "tail -f /var/log/app.log"  # Interactive tail

# You watch everything in real-time
```

### 6. **Multi-Session Management**

```bash
# Start multiple sessions
silc start dev-session --port 20000
silc start prod-session --port 20001

# List all sessions
silc list

# Open Web UI to manage all sessions
silc manager

# Or use native TUI
silc tui
```

### 7. **AI Agent via MCP**

```bash
# Start MCP server for AI agents
silc mcp

# Agent uses MCP tools:
# - list_sessions()
# - send(port, "git status", timeout_ms=5000)
# - read(port, lines=100)
# - send_key(port, "ctrl+c")
# - resize(port, rows=30, cols=120)
```

---

## 📊 SILC vs. Alternatives

| Feature | SILC v3 | Agent Shells | tmux/screen |
|---------|---------|--------------|-------------|
| Your Environment | ✅ Full access | ❌ Isolated | ✅ |
| TUI Apps (vim, htop) | ✅ | ❌ | ✅ |
| Real-time Visibility | ✅ | ❌ | ⚠️ |
| HTTP API | ✅ REST + WebSocket | ❌ | ❌ |
| Agent-Friendly | ✅ MCP + CLI | ✅ | ❌ |
| Human Intervention | ✅ | ❌ | ✅ |
| Web UI | ✅ Browser-based | ❌ | ❌ |
| Native TUI | ✅ Rust-based | ❌ | ❌ |
| Session Sharing | ✅ Multi-user | ❌ | ⚠️ |
| Named Sessions | ✅ Docker-style | ❌ | ❌ |

---

## 🛠️ Installation

```bash
# With uv (recommended - fast)
uv tool install git+https://github.com/lirrensi/silc.git

# With pip (editable install for development)
pip install -e .

# With pipx (global install)
pipx install git+https://github.com/lirrensi/silc.git
```

**Note:** PyPI package coming soon. For now, install from git.

### Building the Web UI

The Web UI is a Vue 3 + Vite application. It builds automatically when packaging, but for development:

```bash
# Build once (auto-detects pnpm, npm, or yarn)
silc-build-web

# Or watch mode (in a separate terminal)
cd manager_web_ui && pnpm dev
```

---

## 🎮 The Manageable VI — All Interfaces

SILC v3 unifies all terminal interaction into one manageable VI:

### CLI (Primary Interface)

**Complete Command Reference:**

```bash
# ═══════════════════════════════════════════════════════════
# DAEMON MANAGEMENT
# ═══════════════════════════════════════════════════════════

silc start [name]              # Start daemon + create session (auto name if not provided)
silc start my-project          # Create named session (e.g., "my-project")
silc start --port 20001        # Create session on specific port
silc start --global --token xyz  # Network-accessible session with token auth
silc start --shell zsh         # Use specific shell (bash, zsh, pwsh, cmd)
silc start --cwd /path/to/dir  # Set working directory for session

silc manager                   # Open Web UI in browser (starts daemon if needed)
silc list                      # List all active sessions (shows port, name, idle time)
silc shutdown                  # Graceful shutdown (closes all sessions)
silc killall                   # Force kill daemon + all sessions
silc resurrect                 # Restore sessions from previous state
silc restart                   # Shutdown + restart (auto-resurrects sessions)
silc restart-server            # Restart HTTP server only (sessions survive)
silc logs [--tail 100]         # Show daemon logs (last N lines)
silc mcp                       # Start MCP server for AI agents

# ═══════════════════════════════════════════════════════════
# SESSION COMMANDS (use port or name)
# ═══════════════════════════════════════════════════════════
# Examples: silc 20000 run "ls"    OR    silc my-project run "ls"

silc <port-or-name> run <cmd>    # Run command (WAITS for completion, returns output)
silc <port-or-name> in <text>    # Send raw input (fire-and-forget, no wait)
silc <port-or-name> out [lines]  # View output (default: last 100 lines)
silc <port-or-name> status       # Show session status (alive, idle, waiting_for_input)
silc <port-or-name> interrupt    # Send Ctrl+C to running process
silc <port-or-name> clear        # Clear terminal screen
silc <port-or-name> reset        # Reset terminal state
silc <port-or-name> resize       # Resize terminal (default: 30x120)
silc <port-or-name> resize --rows 40 --cols 150
silc <port-or-name> close        # Gracefully close session
silc <port-or-name> kill         # Force kill session
silc <port-or-name> logs [--tail 100]  # Show session logs
silc <port-or-name> tui          # Launch native TUI client
silc <port-or-name> web          # Open session Web UI in browser
silc <port-or-name> stream-render <file> [--interval 5]  # Stream rendered output to file
silc <port-or-name> stream-append <file> [--interval 5]  # Append output to file (dedup)
silc <port-or-name> stream-stop <file>   # Stop streaming to file
silc <port-or-name> stream-status        # Show streaming status

# ═══════════════════════════════════════════════════════════
# KEY DISTINCTIONS
# ═══════════════════════════════════════════════════════════

# run vs in (CRITICAL):
silc 20000 run "git status"      # ✅ WAITS for completion (command finishes)
silc 20000 in "vim config.py"    # ✅ Fire-and-forget (interactive app)

# When to use each:
# run: git, npm, pytest, ls, cat, scripts, any command that FINISHES
# in:  vim, htop, SSH, REPLs, docker -it, any INTERACTIVE app

# Named sessions vs ports:
silc start my-project            # Creates session named "my-project"
silc my-project run "ls"         # Use name instead of port
silc 20000 run "ls"              # Same as above (if port 20000)

# Persistence:
silc shutdown                    # Saves sessions to ~/.silc/sessions.json
silc resurrect                   # Restores sessions from previous state
silc restart                     # Shutdown + restart (auto-resurrects)
```

**Named Session Format:**
- Must start with lowercase letter: `[a-z]`
- Can contain: lowercase letters, numbers, hyphens
- Cannot end with hyphen
- Auto-generated format: `adjective-noun-number` (e.g., `happy-fox-42`)
- Examples: ✅ `my-project`, `dev-server-1`, `test123`
- Examples: ❌ `My-Project`, `123test`, `test-`

### REST API

**Daemon API (port 19999):**
```bash
# List all sessions
curl http://127.0.0.1:19999/sessions

# Create session
curl -X POST http://127.0.0.1:19999/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "my-project", "port": 20000, "shell": "bash"}'

# Resolve name to port
curl http://127.0.0.1:19999/resolve/my-project

# Close session
curl -X DELETE http://127.0.0.1:19999/sessions/20000

# Shutdown daemon
curl -X POST http://127.0.0.1:19999/shutdown

# Resurrect sessions
curl -X POST http://127.0.0.1:19999/resurrect
```

**Session API (port 20000+):**
```bash
# Get status
curl http://127.0.0.1:20000/status

# Get output (last N lines)
curl "http://127.0.0.1:20000/out?lines=50"

# Run command (waits for completion - only for commands that FINISH)
curl -X POST http://127.0.0.1:20000/run \
  -H "Content-Type: application/json" \
  -d '{"command": "git status", "timeout": 60}'

# Send raw input (fire-and-forget - for interactive apps)
curl -X POST http://127.0.0.1:20000/in \
  -H "Content-Type: text/plain" \
  -d "vim config.py"

# Interrupt (Ctrl+C)
curl -X POST http://127.0.0.1:20000/interrupt

# Resize terminal
curl -X POST "http://127.0.0.1:20000/resize?rows=40&cols=120"

# Clear screen
curl -X POST http://127.0.0.1:20000/clear

# Close session
curl -X POST http://127.0.0.1:20000/close

# Kill session
curl -X POST http://127.0.0.1:20000/kill

# Get logs
curl "http://127.0.0.1:20000/logs?tail=100"

# WebSocket (real-time streaming)
ws://127.0.0.1:20000/ws
```

**Authentication:** For non-localhost connections, include token:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://host:20000/status
# OR
curl http://host:20000/status?token=YOUR_TOKEN
```

### WebSocket (Real-time Streaming)
```javascript
const ws = new WebSocket('ws://127.0.0.1:20000/ws');
ws.onmessage = (event) => console.log(event.data);
ws.send('ls -la\n');
```

### MCP Server (AI Agent Integration)

```python
# Start MCP server
silc mcp

# Tools available to AI agents (Claude Code, Cursor, Windsurf):

# List all sessions
list_sessions()
# → [{port: 20000, name: "my-project", session_id: "abc123"}]

# Send text to session (waits for output, default 5s timeout)
send(20000, "git status", timeout_ms=5000)
# → {output: "...", lines: 10, alive: true}

# For interactive apps, use timeout_ms=0 (fire-and-forget)
send(20000, "vim config.py", timeout_ms=0)  # Don't wait
# → {output: "", lines: 0, alive: true}

# Then read the screen
read(20000, lines=40)
# → "Current terminal state..."

# Send special keys to control interactive apps
send_key(20000, "ctrl+c")  # Interrupt
send_key(20000, "ctrl+d")  # EOF
send_key(20000, "enter")   # Enter key
send_key(20000, "q")       # Quit (for vim, htop, etc.)
send_key(20000, "escape")  # Escape key

# Resize terminal
resize(20000, rows=40, cols=120)

# Create new session
start_session(port=20001, shell="bash", cwd="/path/to/project")
# → {port: 20001, session_id: "xyz789", name: "auto-generated"}

# Close session
close_session(20000)
```

**Key Design:**
- `send` with `timeout_ms > 0` — waits for output (for commands that complete)
- `send` with `timeout_ms = 0` — fire-and-forget (for interactive apps)
- `read` — get current terminal state
- `send_key` — send special keys (ctrl+c, escape, etc.)
- **Universal** — works in native shell, SSH, Python REPL, htop, any interactive context

### Native TUI (Rust-based)
```bash
silc tui  # Launches fast, native terminal UI
```

### Web UI (Browser-based)
```bash
silc manager  # Opens browser to session management UI
```

---

## 📖 Documentation

**Architecture** (complete enough to rewrite from scratch):
- [Architecture Index](docs/arch_index.md) — Component map
- [Core](docs/arch_core.md) — Session, PTY, buffer, cleaner
- [Daemon](docs/arch_daemon.md) — Session lifecycle management
- [API](docs/arch_api.md) — FastAPI server, endpoints, WebSocket
- [CLI](docs/arch_cli.md) — CLI commands, argument parsing
- [TUI](docs/arch_tui.md) — Native TUI client, installer
- [Web UI](docs/arch_webui.md) — Vue 3 web UI, xterm.js
- [Stream](docs/arch_stream.md) — Streaming service, deduplication
- [MCP](docs/arch_mcp.md) — MCP server for AI agents

**Reference:**
- [Product Specification](docs/product.md) — Features, user flows, architecture
- [Glossary](docs/glossary.md) — Terms and definitions
- [Examples](examples/) — Real-world usage examples

---

## ❓ FAQ

**Q: What's a "manageable VI"?**
A: VI = Virtual Interface. SILC is your single place to work with terminals — not just tmux alternatives, but a unified interface with REST API, WebSocket, TUI, Web UI, and MCP integration.

**Q: Why is CLI the primary interface?**
A: The CLI is simple and intuitive for both humans and AI agents. It provides a consistent interface that works seamlessly with agent workflows. The HTTP API is available for programmatic access.

**Q: How is SILC different from agent shells?**
A: Most agents spawn isolated shells with no access to your environment. SILC gives agents access to YOUR actual shell — your tools, config, aliases, and context. Plus, you can see everything they do and intervene.

**Q: Can agents really use TUI apps like vim?**
A: Yes! SILC supports full PTY emulation, so agents can use any terminal application — vim, htop, git interactive mode, docker containers, REPLs, and more.

**Q: What is the difference between `run` and `in`?**
A: **`run` waits** for the command to FINISH and return to shell prompt (uses sentinel detection). It ONLY works for commands that complete — like `git status`, `npm test`, `ls`. **`in` sends immediately** (fire-and-forget) and MUST be used for interactive apps like vim, htop, SSH, REPLs. Using `run` with vim/htop will hang until timeout.

**Q: When should I use `run` vs `in`?**
A: Use `run` for commands that execute and return: `git status`, `npm test`, `cat file.txt`, `./script.sh`. Use `in` for everything that opens an interactive session: `vim`, `htop`, `ssh`, `python` (REPL), `docker run -it`.

**Q: What is MCP?**
A: MCP (Model Context Protocol) is a standard for AI agent integration. SILC's MCP server lets Claude Code, Cursor, Windsurf, and other MCP-enabled agents control your sessions directly.

**Q: Is SILC secure?**
A: SILC provides real shell access. Never expose to public internet without TLS. Use SSH tunneling for remote access, not `--global` flag. Token-based auth is available for API access.

**Q: Can I use SILC in production?**
A: Yes, but follow security best practices. Use SSH tunneling for remote access, not `--global` flag. Token-based auth and firewall rules are recommended.

**Q: What's the difference between a session and the daemon?**
A: The daemon manages sessions. Each session is an independent shell with its own PTY.

**Q: How do I integrate with my LLM?**
A: Tell your LLM: "I have a SILC session on port 20000. Use `silc 20000 run \"<command>\"` to execute commands and `silc 20000 out` to view output." Or use the MCP server for native integration.

**Q: Can multiple agents work in the same session?**
A: Yes! Multiple agents can collaborate in the same SILC session, maintaining full context and continuity.

**Q: What if an agent runs a bad command?**
A: You can interrupt any command with `silc <port> interrupt` or take over the session at any time. You maintain full control.

**Q: What are named sessions?**
A: Like Docker containers, you can name your sessions (e.g., `my-project`, `dev-server`). SILC resolves names to ports automatically. Format: `[a-z][a-z0-9-]*[a-z0-9]`.

**Q: How does persistence work?**
A: Sessions are saved to `~/.silc/sessions.json` on shutdown. Use `silc resurrect` to restore them. Only metadata persists (port, name, shell, cwd) — not running commands or buffer content.

**Q: What's the difference between `resurrect` and `restart`?**
A: `resurrect` restores sessions from previous state. `restart` shuts down and immediately restarts the daemon (auto-resurrects).

**Q: Can I specify which shell to use?**
A: Yes! Use `silc start --shell zsh` or `silc start --shell pwsh`. Supported: bash, zsh, pwsh, cmd, sh.

**Q: How do I set the working directory?**
A: Use `silc start --cwd /path/to/dir` to set the session's working directory.

**Q: What ports does SILC use?**
A: Daemon runs on port 19999. Sessions start at port 20000 and go up (configurable range: 20000-21000).

**Q: How do I change the port range?**
A: Create `~/.silc/silc.toml` with:
```toml
[ports]
session_start = 20000
session_end = 21000
```

---

## ⚠️ Security

SILC provides **real shell access** to your system:

- Commands run with your user permissions
- Never expose to public internet without TLS
- Use SSH tunneling for remote access: `ssh -L 19999:localhost:19999 user@host`
- Use strong API tokens and firewall rules
- Token-based auth available for API access

**Best practices:**
1. Use `--global` flag only in trusted networks
2. Enable token auth for remote sessions
3. Use SSH tunneling for production access
4. Monitor sessions via Web UI or TUI

---

## 🤝 Contributing

Contributions welcome! Here's how to get started:

```bash
# Fork and clone
git clone https://github.com/lirrensi/silc.git
cd silc

# Set up dev environment
pip install -e .[test]
pre-commit install

# Run tests
pytest tests/

# Run linters
pre-commit run --all-files
```

See [AGENTS.md](AGENTS.md) for development guidelines and [docs/arch_index.md](docs/arch_index.md) for architecture overview.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 💬 Support

- 📖 [Architecture Docs](docs/arch_index.md) — Component documentation
- 📖 [Product Spec](docs/product.md) — Features and user flows
- 💬 [GitHub Discussions](https://github.com/lirrensi/silc/discussions) — Questions and ideas
- 🐛 [Issue Tracker](https://github.com/lirrensi/silc/issues) — Bug reports and feature requests

---

## 📋 Quick Reference

### Common Commands
```bash
silc start                    # Start daemon + session (auto name)
silc start my-project         # Start named session
silc <port-or-name> run "cmd" # Run command that COMPLETES (waits)
silc <port-or-name> in "cmd"  # Send to interactive app (fire-and-forget)
silc <port-or-name> out       # View output
silc list                     # List sessions
silc resurrect                # Restore sessions
silc shutdown                 # Stop daemon
```

### run vs in (MEMORIZE THIS!)
```bash
# run = command FINISHES → use run
silc 20000 run "git status"
silc 20000 run "npm test"
silc 20000 run "ls -la"

# in = interactive app → use in
silc 20000 in "vim file.py"
silc 20000 in "htop"
silc 20000 in "ssh user@server"
```

### Ports
| Port | Purpose |
|------|---------|
| 19999 | Daemon management API |
| 20000-21000 | Session ports (default range) |

### Files
| File | Purpose |
|------|---------|
| `~/.silc/silc.toml` | Configuration |
| `~/.silc/sessions.json` | Persistent session registry |
| `~/.silc/logs/daemon.log` | Daemon log |
| `~/.silc/logs/session_<port>.log` | Session log |

### Environment Variables
```bash
SILC_DATA_DIR=/path/to/data     # Override data directory
SILC_LOG_LEVEL=DEBUG            # Set log level
SILC_COMMAND_TIMEOUT=600        # Default command timeout (seconds)
SILC_MAX_BUFFER_BYTES=5242880   # Max buffer size (5MB default)
```

---

Made with ❤️ for humans and AI agents alike. *Meow.*
