# Architecture Index

This index maps the SILC architecture components. Each component can be rewritten independently without touching others.

---

## Components

| File | Description |
|------|-------------|
| [arch_core.md](arch_core.md) | Session, PTY, buffer, cleaner — the shell interaction layer |
| [arch_daemon.md](arch_daemon.md) | Daemon manager, registry, pidfile — session lifecycle management |
| [arch_api.md](arch_api.md) | FastAPI server, endpoints, WebSocket — HTTP/WebSocket interface |
| [arch_cli.md](arch_cli.md) | CLI commands, argument parsing — command-line interface |
| [arch_tui.md](arch_tui.md) | Native TUI client, installer — terminal user interface |
| [arch_stream.md](arch_stream.md) | Streaming service, deduplication — file output streaming |

---

## Component Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interfaces                          │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   arch_cli.md   │   arch_tui.md   │        arch_api.md          │
│   (CLI)         │   (TUI)         │   (HTTP/WebSocket)          │
└────────┬────────┴────────┬────────┴──────────────┬──────────────┘
         │                 │                       │
         └─────────────────┼───────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ arch_daemon │
                    │   (Daemon)  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │ arch_stream │   │  arch_core  │   │  (Config)   │
  │ (Streaming) │   │  (Session)  │   │  silc/      │
  └─────────────┘   └──────┬──────┘   │  config.py  │
                           │          └─────────────┘
                    ┌──────▼──────┐
                    │    PTY      │
                    │  (Shell)    │
                    └─────────────┘
```

---

## Dependency Graph

```
arch_cli ──────► arch_api ──────► arch_core ──────► PTY
    │                │                │
    │                │                └──► arch_stream
    │                │
    └──► arch_daemon ──────► arch_core
              │
              └──► arch_api

arch_tui ──────► arch_api (WebSocket)
```

---

## Replaceability

Each component can be rewritten in a different language/framework:

| Component | Could Be Rewritten As |
|-----------|----------------------|
| arch_cli | Go CLI, Rust CLI, Shell script |
| arch_tui | Go TUI (bubbletea), Rust TUI (ratatui) |
| arch_api | Flask, Go (gin), Rust (actix-web) |
| arch_daemon | Go, Rust, systemd service |
| arch_core | Rust (portable-pty), Go |
| arch_stream | Any language with file I/O |

---

## Shared Dependencies

All components depend on:

- **Config** (`silc/config.py`) — Configuration loading
- **Persistence** (`silc/utils/persistence.py`) — Logging, data directories
- **Ports** (`silc/utils/ports.py`) — Port management
- **Shell Detect** (`silc/utils/shell_detect.py`) — Shell detection
