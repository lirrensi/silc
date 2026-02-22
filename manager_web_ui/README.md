# SILC Manager Web UI

Browser-based terminal session manager for SILC. View and interact with multiple shell sessions through xterm.js.

## Overview

This is a Vue 3 single-page application that provides:

- **Session Grid** — View all active sessions at a glance
- **Interactive Terminals** — Full terminal emulation via xterm.js
- **Real-time Updates** — WebSocket streaming of terminal output
- **Session Management** — Create, close, and control sessions

## Prerequisites

- Node.js `^20.19.0 || >=22.12.0`
- pnpm (recommended) or npm
- SILC daemon running on `localhost:19999`

## Development

```bash
# Install dependencies
pnpm install

# Start dev server with hot reload
pnpm dev
```

The app will be available at `http://localhost:5173`.

**Note:** The SILC daemon must be running for the web UI to function. Start it with `silc start` or `silc manager`.

## Production Build

```bash
# Type-check and build
pnpm build

# Preview production build
pnpm preview
```

Build output goes to `../static/manager/` for serving by the SILC daemon.

## Access via SILC

The recommended way to use this UI:

```bash
# Open manager in browser (starts daemon if needed)
silc manager
```

This serves the compiled web UI from `static/manager/` via the daemon's HTTP server.

## Architecture

```
src/
├── main.ts                 # Entry point
├── App.vue                 # Root layout
├── router/index.ts         # Vue Router config
├── stores/
│   └── terminalManager.ts  # Pinia store (core state)
├── views/
│   ├── HomeView.vue        # Session grid
│   └── SessionView.vue     # Single session
├── components/
│   ├── Sidebar.vue         # Session list
│   ├── SessionCard.vue     # Preview card
│   └── TerminalViewport.vue # xterm.js wrapper
├── lib/
│   ├── daemonApi.ts        # HTTP client
│   ├── websocket.ts        # WebSocket handling
│   └── idleManager.ts      # Idle cleanup
└── types/session.ts        # TypeScript interfaces
```

See [docs/arch_webui.md](../docs/arch_webui.md) for complete architecture documentation.

## Features

### Terminal Controls

| Button | Action |
|--------|--------|
| SIGINT | Send Ctrl+C (interrupt) |
| SIGTERM | Graceful termination signal |
| SIGKILL | Force kill (nuclear option) |
| Clear | Clear terminal screen |
| Paste | Paste from clipboard |
| ↓ Bottom | Scroll to bottom |
| Arrow keys | Send navigation sequences |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+C | Copy selection (if any) |
| Ctrl+V | Paste from clipboard |
| Right-click | Paste from clipboard |
| Ctrl+Enter | Send modified Enter |
| Shift+Enter | Send modified Enter |

### Status Indicators

| Color | Status |
|-------|--------|
| Green | Active (WebSocket connected) |
| Gray | Idle (disconnected) |
| Red | Dead (session ended) |

## Testing

### Unit Tests (Vitest)

```bash
pnpm test:unit
```

### E2E Tests (Playwright)

```bash
# Install browsers (first time)
npx playwright install

# Run tests
pnpm test:e2e

# Run in debug mode
pnpm test:e2e --debug
```

## Linting

```bash
# Run oxlint + ESLint
pnpm lint

# Format with Prettier
pnpm format
```

## IDE Setup

- [VS Code](https://code.visualstudio.com/)
- [Vue - Official](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (disable Vetur)
- [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)

## Related Documentation

- [SILC Product Spec](../docs/product.md)
- [Architecture Index](../docs/arch_index.md)
- [Web UI Architecture](../docs/arch_webui.md)
- [API Architecture](../docs/arch_api.md)
