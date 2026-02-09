# SILC (Shared Interactive Linked CMD)

[![PyPI version](https://badge.fury.io/py/silc.svg)](https://badge.fury.io/py/silc)
[![Python Version](https://img.shields.io/pypi/pyversions/silc.svg)](https://pypi.org/project/silc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://github.com/lirrensi/silc/workflows/CI/badge.svg)](https://github.com/lirrensi/silc/actions)
[![codecov](https://codecov.io/gh/lirrensi/silc/branch/main/graph/badge.svg)](https://codecov.io/gh/lirrensi/silc)
[![GitHub stars](https://img.shields.io/github/stars/lirrensi/silc?style=social)](https://github.com/lirrensi/silc/stargazers)

**Bridge your terminal with the world - let humans and AI agents collaborate in the same shell.**

---

## 🎯 The Problem

Most AI coding agents (Claude, GPT-4, Cursor, etc.) spawn their own isolated shells when they need to execute commands. This creates major limitations:

- ❌ **No access to your environment** - They can't see your installed tools, aliases, or configuration
- ❌ **No context continuity** - Each command runs in a fresh, isolated environment
- ❌ **Can't use TUI apps** - They can't use `vim`, `htop`, `git interactive`, or any terminal UI
- ❌ **Limited debugging** - You can't see what they're doing in real-time or intervene
- ❌ **No collaboration** - You and the agent can't work together in the same session

## ✨ The SILC Solution

SILC gives AI agents **direct access to YOUR shell** while keeping you in control:

- ✅ **Full environment access** - Agents work in your actual shell with all your tools and config
- ✅ **Real-time visibility** - See exactly what the agent is doing as it happens
- ✅ **Interactive TUI support** - Agents can use `vim`, `htop`, `git`, and any terminal app
- ✅ **Human-in-the-loop** - Monitor, interrupt, or take over at any moment
- ✅ **True collaboration** - Work side-by-side with AI agents in the same session

## 💡 CLI-First Design

SILC is designed to be used primarily through its **CLI commands** - the same interface for both you and AI agents:

```bash
# You use it
silc 20000 run "git status"
silc 20000 run "vim config.json"

# Agent uses it (same commands!)
silc 20000 run "npm test"
silc 20000 run "htop"
```

The HTTP API and WebSocket are available for programmatic access, but the **CLI is the primary and recommended interface**.

---

---

## What is SILC?

SILC transforms your terminal session into a programmable interface, enabling **seamless collaboration between you and AI agents** in your actual shell environment.

### The Problem with AI Coding Agents

Most AI coding agents (Claude, GPT-4, Cursor, etc.) spawn their own isolated shells when they need to execute commands. This has major limitations:

- ❌ **No access to your environment** - They can't see your installed tools, aliases, or configuration
- ❌ **No context continuity** - Each command runs in a fresh, isolated environment
- ❌ **Can't interact with TUI apps** - They can't use `vim`, `htop`, `git interactive`, or any terminal UI
- ❌ **Limited debugging** - You can't see what they're doing in real-time or intervene
- ❌ **No collaboration** - You and the agent can't work together in the same session

### The SILC Solution

SILC gives AI agents **direct access to YOUR shell** while keeping you in control:

- ✅ **Full environment access** - Agents work in your actual shell with all your tools and config
- ✅ **Real-time visibility** - See exactly what the agent is doing as it happens
- ✅ **Interactive TUI support** - Agents can use `vim`, `htop`, `git`, and any terminal app
- ✅ **Human-in-the-loop** - Monitor, interrupt, or take over at any moment
- ✅ **True collaboration** - Work side-by-side with AI agents in the same session

### How It Works

**CLI-first approach** - SILC is designed to be used primarily through its CLI commands:

```bash
# Start a session
silc start

# You work in your terminal normally
vim myapp.py
npm test
git commit -m "fix bug"

# Agent can also work in the SAME session
silc 20000 run "git status"
silc 20000 run "npm install"
silc 20000 run "vim config.json"  # Yes, even vim!
```

The HTTP API and WebSocket are available for programmatic access, but the **CLI is the primary and recommended interface** for both humans and agents.

---

## Agent + Human Collaboration Patterns

SILC enables powerful new ways to work with AI agents:

### 1. **Open SSH and Ask Agent to Work Inside**

```bash
# SSH into your server
ssh user@production-server

# Start SILC
silc start

# Now ask your AI agent to work in this session:
# "Please deploy the new version and monitor the logs"
# Agent executes: silc 20000 run "./deploy.sh"
# Agent monitors: silc 20000 out
# You can watch everything in real-time
```

### 2. **Monitor Long-Running Processes**

```bash
# Start a long-running task
silc 20000 run "nohup python train_model.py &"

# Agent monitors it for you
# "Watch this training job and alert me if it fails"
# Agent periodically checks: silc 20000 out
# Agent alerts you: "Training failed at epoch 5, error: out of memory"
```

### 3. **Use CLI Exactly as Human Would**

```bash
# Agent can use ANY CLI tool, including TUI apps:
silc 20000 run "htop"              # System monitoring
silc 20000 run "vim main.py"       # Edit files
silc 20000 run "git rebase -i"     # Interactive git
silc 20000 run "docker run -it ubuntu"  # Interactive containers
silc 20000 run "python manage.py shell"  # REPLs
```

### 4. **Collaborative Debugging**

```bash
# You're debugging an issue
silc 20000 run "python -m pytest tests/test_api.py"

# Test fails, you ask agent to investigate
# Agent runs: silc 20000 run "cat logs/error.log"
# Agent runs: silc 20000 run "vim tests/test_api.py"
# Agent suggests fix, you review and apply
```

### 5. **Agent as Your Terminal Assistant**

```bash
# You're working, agent watches and helps
# You: "Set up a development environment for this project"
# Agent: silc 20000 run "python -m venv venv"
# Agent: silc 20000 run "source venv/bin/activate"
# Agent: silc 20000 run "pip install -r requirements.txt"
# You can see everything and intervene if needed
```

---

## Why SILC?

---

## Why SILC?

### SILC vs. AI Agent Shells

| Feature | SILC | Agent Isolated Shells |
|---------|------|----------------------|
| Your Environment | ✅ Full access | ❌ Fresh/clean env |
| Your Aliases/Config | ✅ Available | ❌ Not available |
| TUI App Support | ✅ vim, htop, git | ❌ Only simple commands |
| Real-time Visibility | ✅ Watch everything | ❌ Black box |
| Human Intervention | ✅ Take over anytime | ❌ Can't intervene |
| Context Continuity | ✅ Same session | ❌ Each command isolated |
| Debugging | ✅ See what happens | ❌ Hard to debug |

### SILC vs. Traditional Tools

| Feature | SILC | tmux/screen | SSH | Docker Exec |
|---------|------|-------------|-----|-------------|
| HTTP API | ✅ | ❌ | ❌ | ❌ |
| AI Agent Friendly | ✅ | ❌ | ❌ | ⚠️ |
| CLI-First Design | ✅ | ⚠️ | ⚠️ | ⚠️ |
| Real-time Streaming | ✅ | ✅ | ✅ | ✅ |
| Cross-platform | ✅ | ⚠️ | ✅ | ✅ |
| Programmatic Access | ✅ | ❌ | ⚠️ | ⚠️ |
| Session Persistence | ✅ | ✅ | ❌ | ❌ |
| Web UI | ✅ | ❌ | ❌ | ❌ |

### When to Use SILC

**Perfect for AI + Human Collaboration:**
- 🤖 **AI agents** that need to work in YOUR environment
- 👤 **You** want to monitor and control what agents do
- 🔄 **Collaborative debugging** - work together with AI
- 📊 **Agent-assisted monitoring** - let agents watch processes for you
- 🛠️ **Agent as terminal assistant** - have AI help with CLI tasks

**Also Great For:**
- Creating web-based terminal interfaces
- Automating shell operations via HTTP
- Sharing terminal sessions with teams
- Building custom terminal-based tools

### Key Differentiator: Control + Accessibility

SILC gives you **both** control and accessibility:

- **Control**: You see everything agents do, can interrupt anytime, and maintain full ownership of your shell
- **Accessibility**: Agents can use your environment exactly as you would - including TUI apps, your config, and your tools
- **Flexibility**: Works with any agent (Claude, GPT-4, Cursor, etc.) and any workflow

Unlike isolated agent shells that limit what agents can do, SILC removes those limitations while keeping you in the driver's seat.

---

## Quick Start (5 minutes)

### Prerequisites
- Python 3.12 or later
- Windows, Linux, or macOS

### Step 1: Install (30 seconds)

```bash
pip install -e .
```

### Step 2: Start SILC (10 seconds)

```bash
silc start
```

**Output:**
```
✓ SILC daemon started on port 19999
✓ Session created on port 20000
```

### Step 3: Use SILC via CLI (Recommended)

The **CLI is the primary way to interact with SILC** - for both you and AI agents:

```bash
# Run commands in your session
silc 20000 run "echo 'Hello from SILC!'"
silc 20000 run "ls -la"
silc 20000 run "git status"

# View output anytime
silc 20000 out

# Check session status
silc 20000 status

# List all sessions
silc list
```

### Step 4: Try with TUI Apps (10 seconds)

SILC supports interactive terminal apps - something most agent shells can't do:

```bash
# Use vim through SILC
silc 20000 run "vim test.txt"

# Use htop for monitoring
silc 20000 run "htop"

# Interactive git operations
silc 20000 run "git rebase -i HEAD~3"
```

### Step 5: Agent Integration (30 seconds)

Now your AI agent can work in YOUR shell:

```python
import requests

# Agent runs commands in YOUR environment
response = requests.post("http://localhost:20000/run", json={
    "command": "git status"
})
print(response.json()["output"])

# Agent can use YOUR tools and config
response = requests.post("http://localhost:20000/run", json={
    "command": "npm test"  # Uses your npm, your config
})
```

🎉 **Congratulations! You've just set up SILC for human + AI collaboration.**

**Next:** Tell your AI agent: "I have a SILC session running on port 20000. You can run commands using `silc 20000 run \"<command>\"` and view output with `silc 20000 out`."

---

## Features

### CLI-First Design
- 💻 **Primary CLI interface** - Designed to be used via command line
- 🎯 **Simple commands** - Intuitive syntax for humans and agents alike
- 🔄 **Session management** - Easy create, list, and manage sessions
- 📤 **Output viewing** - View session output anytime with `silc <port> out`
- ⚡ **Quick execution** - Run commands with `silc <port> run "<cmd>"`

### Agent + Human Collaboration
- 🤖 **Full environment access** - Agents work in YOUR shell with your tools
- 👀 **Real-time visibility** - See exactly what agents are doing
- 🛑 **Human control** - Interrupt, take over, or monitor at any time
- 🎨 **TUI app support** - Agents can use vim, htop, git, and any terminal app
- 🔄 **Context continuity** - Same session for all commands

### Core Capabilities
- 🚀 **One-command setup** - Start daemon and create sessions instantly
- 🔌 **HTTP API** - Full REST API for programmatic access
- 📡 **WebSocket Streaming** - Real-time terminal output
- 🌐 **Cross-platform** - Windows, Linux, macOS support
- 🎨 **Native TUI** - Beautiful terminal interface (Rust-based)

### Advanced Features
- 🔐 **Token-based Auth** - Secure remote access
- 📊 **Session Management** - Multiple concurrent sessions
- 💾 **Output Buffering** - Configurable output history
- 🔄 **Command History** - Track executed commands
- 📝 **Logging** - Comprehensive session and daemon logs

### Developer-Friendly
- 🐍 **Python-first** - Easy to extend and integrate
- 📦 **PyPI Package** - Simple installation
- 🧪 **Well-tested** - Comprehensive test suite
- 📚 **Extensive Docs** - Detailed API documentation
- 🔧 **Configurable** - TOML-based configuration

---

## Use Cases

### 1. 🤖 AI Agent Working in Your Environment

**Problem:** AI agents spawn isolated shells with no access to your tools, config, or context.

**Solution with SILC:**
```python
import requests

# Agent works in YOUR actual shell
response = requests.post("http://localhost:20000/run", json={
    "command": "git status"  # Uses your git config
})
output = response.json()["output"]

# Agent can use YOUR installed tools
response = requests.post("http://localhost:20000/run", json={
    "command": "npm test"  # Uses your npm, your node_modules
})

# Agent can use YOUR aliases and functions
response = requests.post("http://localhost:20000/run", json={
    "command": "my-custom-alias"  # Your .bashrc aliases work!
})
```

**Result:** Agent has full access to your environment while you maintain control.

---

### 2. 👀 Monitor Long-Running Processes

**Problem:** You need to run long tasks but want AI to monitor and alert you.

**Solution with SILC:**
```bash
# Start a long-running task
silc 20000 run "nohup python train_model.py &"

# Tell agent: "Monitor this training and alert me if it fails"
# Agent periodically checks:
silc 20000 out

# Agent alerts you: "Training failed at epoch 5 with error: out of memory"
# You can then investigate:
silc 20000 run "cat logs/training.log"
```

**Result:** AI watches your processes while you focus on other work.

---

### 3. 🛠️ Collaborative Debugging

**Problem:** You're stuck on a bug and want AI to help investigate in your actual environment.

**Solution with SILC:**
```bash
# You run tests
silc 20000 run "pytest tests/test_api.py"

# Tests fail, you ask agent to investigate
# Agent runs: silc 20000 run "cat logs/error.log"
# Agent runs: silc 20000 run "vim tests/test_api.py"
# Agent suggests: "Line 42 has a typo - change 'fale' to 'false'"

# You review and apply the fix
silc 20000 run "vim tests/test_api.py"  # You make the change
silc 20000 run "pytest tests/test_api.py"  # Tests pass!
```

**Result:** True collaboration - you and AI work together in the same session.

---

### 4. 🖥️ Agent Uses TUI Apps

**Problem:** Most agent shells can't use interactive terminal apps like vim, htop, or git.

**Solution with SILC:**
```bash
# Agent can use vim to edit files
silc 20000 run "vim config.json"

# Agent can use htop for system monitoring
silc 20000 run "htop"

# Agent can do interactive git operations
silc 20000 run "git rebase -i HEAD~3"

# Agent can use any CLI tool you have
silc 20000 run "docker run -it ubuntu bash"
silc 20000 run "python manage.py shell"
silc 20000 run "ncdu"  # Disk usage analyzer
```

**Result:** Agents can use ANY terminal tool, just like you.

---

### 5. 🚀 Remote Server Management

**Problem:** You need AI to work on a remote server but want to monitor and control it.

**Solution with SILC:**
```bash
# SSH into your server
ssh user@production-server

# Start SILC
silc start

# Tell agent: "Deploy the new version and monitor the logs"
# Agent executes:
silc 20000 run "./deploy.sh"
silc 20000 run "tail -f /var/log/app.log"

# You watch everything in real-time via:
silc 20000 out

# If something goes wrong, you can take over immediately
silc 20000 run "systemctl restart myapp"
```

**Result:** AI works on your servers while you maintain full visibility and control.

---

### 6. 📊 Agent as Terminal Assistant

**Problem:** You want AI to help with CLI tasks but don't want to give up control.

**Solution with SILC:**
```bash
# You're setting up a new project
# You say: "Set up a Python development environment"

# Agent handles it:
silc 20000 run "python -m venv venv"
silc 20000 run "source venv/bin/activate"
silc 20000 run "pip install -r requirements.txt"
silc 20000 run "pre-commit install"

# You can see every step and intervene if needed
silc 20000 out

# You continue working normally
vim main.py
pytest tests/
```

**Result:** AI assists with setup and automation while you stay in control.

---

### 7. 🔄 Multi-Agent Collaboration

**Problem:** Multiple AI agents need to work together in the same environment.

**Solution with SILC:**
```bash
# Agent 1 sets up the environment
silc 20000 run "npm install"

# Agent 2 runs tests
silc 20000 run "npm test"

# Agent 3 deploys if tests pass
silc 20000 run "npm run deploy"

# All agents work in the SAME session with full context
# You can monitor everything:
silc 20000 out
```

**Result:** Multiple agents collaborate seamlessly in your environment.

See [examples/](examples/) for more real-world examples and code samples.

---

## Installation

### Using pip (recommended)

```bash
pip install -e .
```

### Using pipx (isolated environment)

```bash
pipx install git+https://github.com/lirrensi/silc.git
```

### Using uv (fast)

```bash
uv tool install git+https://github.com/lirrensi/silc.git
```

### Standalone Installer (no pip required)

**Windows:**
```cmd
install.bat
```

**Unix/Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

---

## Common Commands

**The CLI is the primary and recommended way to interact with SILC** - for both humans and AI agents.

| Command | Description | Example |
|---------|-------------|---------|
| `silc start` | Start daemon and create session | `silc start` |
| `silc create` | Create new session | `silc create --port 20001` |
| `silc <port> run "<cmd>"` | Execute command in session | `silc 20000 run "ls -la"` |
| `silc <port> out` | View session output | `silc 20000 out` |
| `silc <port> status` | Check session status | `silc 20000 status` |
| `silc <port> tui` | Launch TUI for session | `silc 20000 tui` |
| `silc <port> interrupt` | Send Ctrl+C to session | `silc 20000 interrupt` |
| `silc list` | List all sessions | `silc list` |
| `silc shutdown` | Stop daemon | `silc shutdown` |

### Agent Usage Pattern

When working with AI agents, simply tell them:

> "I have a SILC session running on port 20000. You can run commands using `silc 20000 run \"<command>\"` and view output with `silc 20000 out`."

The agent can then:
```bash
# Run commands
silc 20000 run "git status"
silc 20000 run "npm test"
silc 20000 run "vim config.json"

# View output
silc 20000 out

# Check status
silc 20000 status
```

See [docs/commands_and_api.md](docs/commands_and_api.md) for complete command reference.

---

## Documentation

- [Getting Started Guide](docs/getting-started.md) - Detailed setup guide
- [User Guide](docs/user-guide.md) - Comprehensive usage guide
- [API Reference](docs/commands_and_api.md) - CLI and REST API docs
- [Configuration](docs/configuration.md) - Setup and customization
- [Architecture](docs/architecture.md) - System design and components
- [Examples](examples/) - Real-world usage examples

---

## Docker Mode

Run SILC in Docker for a sandboxed shell with HTTP API access:

```bash
docker-compose up -d

# Access sessions via HTTP
curl http://localhost:19999/sessions
curl http://localhost:20000/status
```

Perfect for:
- Clean, isolated shell environments
- Consistent environments across machines
- Giving agents a disposable workspace

---

## FAQ

**Q: Why is CLI the primary interface?**
A: The CLI is designed to be simple and intuitive for both humans and AI agents. It provides a consistent, easy-to-use interface that works seamlessly with agent workflows. The HTTP API and WebSocket are available for programmatic access, but the CLI is recommended for most use cases.

**Q: How is SILC different from agent shells?**
A: Most AI agents spawn isolated shells with no access to your environment. SILC gives agents access to YOUR actual shell - your tools, config, aliases, and context. Plus, you can see everything they do and intervene at any time.

**Q: Can agents really use TUI apps like vim?**
A: Yes! SILC supports full PTY emulation, so agents can use any terminal application - vim, htop, git interactive mode, docker containers, REPLs, and more. This is something most agent shells can't do.

**Q: Is SILC secure?**
A: SILC provides real shell access. Never expose to public internet without TLS. See [Security Considerations](#security-considerations).

**Q: Can I use SILC in production?**
A: Yes, but follow security best practices. Use SSH tunneling for remote access, not `--global` flag.

**Q: What's the difference between a session and the daemon?**
A: The daemon manages sessions. Each session is an independent shell with its own PTY.

**Q: How do I integrate with my LLM?**
A: Simply tell your LLM: "I have a SILC session on port 20000. Use `silc 20000 run \"<command>\"` to execute commands and `silc 20000 out` to view output." See [examples/llm_integration.py](examples/llm_integration.py) for a complete example.

**Q: Can multiple agents work in the same session?**
A: Yes! Multiple agents can collaborate in the same SILC session, maintaining full context and continuity. This is perfect for multi-agent workflows.

**Q: What if an agent runs a bad command?**
A: You can interrupt any command with `silc <port> interrupt` or take over the session at any time. You maintain full control and visibility.

See [docs/faq.md](docs/faq.md) for more FAQs.

---

## Security Considerations

⚠️ **Important Security Notes:**

### Real Shell Access
SILC provides **real shell access** to your system:
- Commands run with your user permissions
- You can delete files, modify system settings, etc.
- **Never run untrusted commands** in SILC sessions
- Be cautious when sharing session access with agents or others

### Global Sessions (--global flag)
When using the `--global` flag:
- **Tokens are sent over plaintext HTTP** (not encrypted)
- Anyone on your network can intercept tokens
- **Only use on trusted home networks**
- **Never expose to the public internet**
- Consider using a VPN or reverse proxy with TLS for remote access

### Best Practices
1. **Never expose SILC to the public internet** without proper authentication and TLS
2. Use strong, unique API tokens
3. Regularly review session logs for suspicious activity
4. Close sessions when not in use
5. Keep SILC updated to the latest version
6. Use firewall rules to restrict access to SILC ports

### Recommended Setup for Remote Access
If you need remote access:
1. Use SSH tunneling instead of `--global`:
   ```bash
   ssh -L 19999:localhost:19999 user@remote-host
   ```
2. Or set up a reverse proxy with TLS (nginx, traefik, etc.)
3. Use VPN for secure network access

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- 📖 [Documentation](docs/)
- 💬 [GitHub Discussions](https://github.com/lirrensi/silc/discussions)
- 🐛 [Issue Tracker](https://github.com/lirrensi/silc/issues)

---

**Made with ❤️ for humans and AI agents alike**