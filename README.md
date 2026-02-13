# SILC (Shared Interactive Linked CMD)

[![PyPI version](https://badge.fury.io/py/silc.svg)](https://badge.fury.io/py/silc)
[![Python Version](https://img.shields.io/pypi/pyversions/silc.svg)](https://pypi.org/project/silc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://github.com/lirrensi/silc/workflows/CI/badge.svg)](https://github.com/lirrensi/silc/actions)
[![codecov](https://codecov.io/gh/lirrensi/silc/branch/main/graph/badge.svg)](https://codecov.io/gh/lirrensi/silc)

**Bridge your terminal with the world — let humans and AI agents collaborate in the same shell.**

---

## 🎯 The Problem

Most AI coding agents (Claude, GPT-4, Cursor, etc.) spawn isolated shells with no access to your environment:

- ❌ **No access to your tools** - Can't see your aliases, config, or installed programs
- ❌ **No context continuity** - Each command runs in a fresh, isolated environment
- ❌ **Can't use TUI apps** - vim, htop, git interactive don't work
- ❌ **No visibility** - You can't see what they're doing or intervene
- ❌ **No collaboration** - You and the agent can't work together

## ✨ The SILC Solution

SILC gives AI agents **direct access to YOUR shell** while keeping you in control:

- ✅ **Full environment access** - Agents work in your actual shell with all your tools
- ✅ **Real-time visibility** - See exactly what agents are doing as it happens
- ✅ **Interactive TUI support** - Agents can use vim, htop, git, and any terminal app
- ✅ **Human-in-the-loop** - Monitor, interrupt, or take over at any moment
- ✅ **True collaboration** - Work side-by-side with AI agents in the same session

## 🚀 Quick Start

```bash
# Install
pip install -e .

# Start a session
silc start

# Run commands (you or agent)
silc 20000 run "git status"
silc 20000 run "vim config.json"
silc 20000 run "htop"

# View output
silc 20000 out
```

**That's it!** Your AI agent can now work in YOUR shell environment.

---

## 💡 How It Works

SILC transforms your terminal into a programmable interface with a simple CLI:

```bash
# Start SILC daemon
silc start

# Create a session on port 20000
silc create --port 20000

# Run commands in your actual shell
silc 20000 run "npm test"
silc 20000 run "python -m pytest"
silc 20000 run "vim main.py"

# Watch what happens
silc 20000 out
```

The CLI is the primary interface — simple for humans, perfect for agents. An HTTP API and WebSocket are available for programmatic access.

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
silc 20000 run "vim tests/test_api.py"

# Agent suggests fix, you apply it
```

### 3. **Monitor Long-Running Processes**

```bash
# Start a task
silc 20000 run "nohup python train.py &"

# Agent monitors and alerts you
# "Training failed at epoch 5: out of memory"
```

### 4. **Agent Uses TUI Apps**

```bash
# Agents can use ANY terminal app
silc 20000 run "vim config.json"
silc 20000 run "htop"
silc 20000 run "git rebase -i HEAD~3"
silc 20000 run "docker run -it ubuntu bash"
```

### 5. **Remote Server Management**

```bash
# SSH into server
ssh user@production-server

# Start SILC
silc start

# Agent deploys and monitors
silc 20000 run "./deploy.sh"
silc 20000 run "tail -f /var/log/app.log"

# You watch everything in real-time
```

---

## 📊 SILC vs. Alternatives

| Feature | SILC | Agent Shells | tmux/screen |
|---------|------|--------------|-------------|
| Your Environment | ✅ Full access | ❌ Isolated | ✅ |
| TUI Apps (vim, htop) | ✅ | ❌ | ✅ |
| Real-time Visibility | ✅ | ❌ | ⚠️ |
| HTTP API | ✅ | ❌ | ❌ |
| Agent-Friendly | ✅ | ✅ | ❌ |
| Human Intervention | ✅ | ❌ | ✅ |

---

## 🛠️ Installation

```bash
# Recommended
pip install -e .

# With pipx
pipx install git+https://github.com/lirrensi/silc.git

# With uv
uv tool install git+https://github.com/lirrensi/silc.git
```

---

## 📖 Documentation

- [Getting Started](docs/getting-started.md) - Detailed setup guide
- [User Guide](docs/user-guide.md) - Comprehensive usage guide
- [CLI & API Reference](docs/commands_and_api.md) - Complete command reference
- [Configuration](docs/configuration.md) - Setup and customization
- [Architecture](docs/architecture.md) - System design
- [Examples](examples/) - Real-world usage examples

---

## ❓ FAQ

**Q: Why is CLI the primary interface?**
A: The CLI is simple and intuitive for both humans and AI agents. It provides a consistent interface that works seamlessly with agent workflows. The HTTP API is available for programmatic access.

**Q: How is SILC different from agent shells?**
A: Most agents spawn isolated shells with no access to your environment. SILC gives agents access to YOUR actual shell — your tools, config, aliases, and context. Plus, you can see everything they do and intervene.

**Q: Can agents really use TUI apps like vim?**
A: Yes! SILC supports full PTY emulation, so agents can use any terminal application — vim, htop, git interactive mode, docker containers, REPLs, and more.

**Q: Is SILC secure?**
A: SILC provides real shell access. Never expose to public internet without TLS. Use SSH tunneling for remote access, not `--global` flag.

**Q: Can I use SILC in production?**
A: Yes, but follow security best practices. Use SSH tunneling for remote access, not `--global` flag.

**Q: What's the difference between a session and the daemon?**
A: The daemon manages sessions. Each session is an independent shell with its own PTY.

**Q: How do I integrate with my LLM?**
A: Tell your LLM: "I have a SILC session on port 20000. Use `silc 20000 run \"<command>\"` to execute commands and `silc 20000 out` to view output."

**Q: Can multiple agents work in the same session?**
A: Yes! Multiple agents can collaborate in the same SILC session, maintaining full context and continuity.

**Q: What if an agent runs a bad command?**
A: You can interrupt any command with `silc <port> interrupt` or take over the session at any time. You maintain full control.

See [docs/faq.md](docs/faq.md) for more FAQs.

---

## ⚠️ Security

SILC provides **real shell access** to your system:

- Commands run with your user permissions
- Never expose to public internet without TLS
- Use SSH tunneling for remote access: `ssh -L 19999:localhost:19999 user@host`
- Use strong API tokens and firewall rules
- See [docs/security.md](docs/security.md) for detailed guidelines

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 💬 Support

- 📖 [Documentation](docs/)
- 💬 [GitHub Discussions](https://github.com/lirrensi/silc/discussions)
- 🐛 [Issue Tracker](https://github.com/lirrensi/silc/issues)

---

**Made with ❤️ for humans and AI agents alike**