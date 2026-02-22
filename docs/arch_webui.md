# Architecture: Manager Web UI

This document describes the Vue 3 web application for managing SILC terminal sessions. Complete enough to rewrite `manager_web_ui/` from scratch.

---

## Overview

The Manager Web UI is a single-page application (SPA) that provides:

- **Session Management** — View, create, and close terminal sessions
- **Terminal Access** — Interactive terminal emulation via xterm.js
- **Real-time Updates** — WebSocket streaming of terminal output
- **Multi-session View** — Grid view of all active sessions

Users access it via `silc manager` command, which opens the browser to the web UI.

---

## Scope Boundary

**This component owns:**
- Vue 3 application structure
- Pinia state management
- xterm.js terminal emulation
- WebSocket connection management
- Daemon API client
- Session lifecycle UI

**This component does NOT own:**
- Session PTY management (see [arch_core.md](arch_core.md))
- HTTP/WebSocket server (see [arch_api.md](arch_api.md))
- Daemon process (see [arch_daemon.md](arch_daemon.md))

**Boundary interfaces:**
- Consumes: Daemon API at `http://127.0.0.1:19999`
- Consumes: Session WebSocket at `ws://127.0.0.1:<port>/ws`
- Produces: Static files built to `static/manager/`

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Vue | 3.5+ | UI framework |
| Vue Router | 5.x | Client-side routing |
| Pinia | 3.x | State management |
| xterm.js | 6.x | Terminal emulation |
| Tailwind CSS | 4.x | Styling |
| Vite | 7.x | Build tool |
| TypeScript | 5.x | Type safety |
| Vitest | 4.x | Unit testing |
| Playwright | 1.x | E2E testing |

**Node.js Requirement:** `^20.19.0 || >=22.12.0`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Vue Application                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │   Sidebar   │    │  HomeView   │    │     SessionView         │ │
│  │  (session   │    │  (session   │    │  (interactive terminal) │ │
│  │   list)     │    │   grid)     │    │                         │ │
│  └──────┬──────┘    └──────┬──────┘    └───────────┬─────────────┘ │
│         │                  │                       │               │
│         │    ┌─────────────┴─────────────┐         │               │
│         │    │                           │         │               │
│         │    ▼                           ▼         ▼               │
│  ┌──────┴──────────────────────────────────────────────────────┐  │
│  │                     TerminalManager (Pinia Store)            │  │
│  │  ┌─────────────────────────────────────────────────────────┐ │  │
│  │  │ Session Map: port → { terminal, ws, status, ... }       │ │  │
│  │  └─────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │                                     │
├───────────────────────────────┼─────────────────────────────────────┤
│                               │                                     │
│  ┌────────────────────────────┴────────────────────────────────┐   │
│  │                    Client Libraries                          │   │
│  ├─────────────────┬───────────────────┬───────────────────────┤   │
│  │   daemonApi.ts  │   websocket.ts    │    idleManager.ts     │   │
│  │  (HTTP client)  │  (WS connection)  │   (idle cleanup)      │   │
│  └────────┬────────┴─────────┬─────────┴───────────────────────┘   │
│           │                  │                                     │
└───────────┼──────────────────┼─────────────────────────────────────┘
            │                  │
            ▼                  ▼
     ┌──────────────┐   ┌──────────────┐
     │ Daemon API   │   │ Session WS   │
     │ :19999       │   │ :<port>/ws   │
     └──────────────┘   └──────────────┘
```

---

## Directory Structure

```
manager_web_ui/
├── src/
│   ├── main.ts                 # App entry point
│   ├── App.vue                 # Root component (layout)
│   ├── router/
│   │   └── index.ts            # Vue Router config
│   ├── stores/
│   │   └── terminalManager.ts  # Pinia store (session state)
│   ├── views/
│   │   ├── HomeView.vue        # Session grid view
│   │   └── SessionView.vue     # Single session view
│   ├── components/
│   │   ├── Sidebar.vue         # Session list sidebar
│   │   ├── SessionCard.vue     # Session preview card
│   │   └── TerminalViewport.vue # xterm.js container
│   ├── lib/
│   │   ├── daemonApi.ts        # Daemon HTTP client
│   │   ├── websocket.ts        # WebSocket management
│   │   └── idleManager.ts      # Idle session cleanup
│   ├── types/
│   │   └── session.ts          # TypeScript interfaces
│   └── assets/
│       └── main.css            # Global styles
├── e2e/
│   └── vue.spec.ts             # Playwright E2E tests
├── index.html                  # HTML entry
├── vite.config.ts              # Vite configuration
├── vitest.config.ts            # Vitest configuration
├── playwright.config.ts        # Playwright configuration
├── tsconfig.json               # TypeScript config
├── package.json                # Dependencies
└── README.md                   # Development guide
```

---

## Core Components

### TerminalManager Store

The central Pinia store managing all session state.

**State:**
```typescript
interface Session {
  port: number
  sessionId: string
  name: string
  shell: string
  cwd: string | null
  terminal: Terminal           // xterm.js instance
  fitAddon: FitAddon           // xterm fit addon
  ws: WebSocket | null         // WebSocket connection
  onDataDisposable: IDisposable | null  // Terminal input handler
  status: SessionStatus        // 'active' | 'idle' | 'dead'
  lastActivity: number         // Timestamp for idle tracking
  writeQueue: string[]         // Buffered writes
  writePending: boolean        // Write in progress flag
}

// Store state
sessions: Map<number, Session>
focusedPort: number | null
```

**Getters:**
```typescript
sessionList: Session[]      // Sorted by port
focusedSession: Session | null
activeCount: number
```

**Actions:**
```typescript
createSession(port, sessionId, shell, name?, cwd?): Session
getSession(port): Session | undefined
removeSession(port): void
setFocused(port | null): void
attach(port, container: HTMLElement): void
detach(port): void
fit(port): Promise<void>
setStatus(port, status): void
setWs(port, ws | null): void
safeWrite(port, data: string): void
```

**Terminal Configuration:**
```typescript
{
  cols: 120,
  rows: 30,
  scrollback: 5000,
  convertEol: true,
  allowProposedApi: true,
  theme: {
    background: '#1e1e1e',
    foreground: '#ffffff',
    cursor: '#ff80bf',
    selectionBackground: '#ff80bf44',
  },
  fontFamily: 'Menlo, Monaco, "Courier New", monospace',
  fontSize: 15,
  cursorBlink: true,
}
```

**Terminal Limits:**
- Maximum columns: 256
- Maximum rows: 64

---

### Daemon API Client

HTTP client for the daemon management API.

**Base URL:** `http://127.0.0.1:19999`

**Types:**
```typescript
interface DaemonSession {
  port: number
  name: string
  session_id: string
  shell: string
  cwd: string | null
  idle_seconds: number
  alive: boolean
}

interface CreateSessionResponse {
  port: number
  session_id: string
  shell: string
}
```

**Functions:**
```typescript
listSessions(): Promise<DaemonSession[]>
createSession(options?: { port?, shell?, cwd? }): Promise<CreateSessionResponse>
closeSession(port: number): Promise<void>
resizeSession(port: number, rows: number, cols: number): Promise<void>
sendSigterm(port: number): Promise<void>
sendSigkill(port: number): Promise<void>
sendInterrupt(port: number): Promise<void>
```

---

### WebSocket Manager

Manages WebSocket connections to session endpoints.

**Connection URL:** `ws://127.0.0.1:<port>/ws`

**Protocol:**
- Protocol selection: `wss:` if page is HTTPS, otherwise `ws:`

**Server Messages:**
```typescript
// Output update
{ event: "update", data: "terminal output..." }

// History response
{ event: "history", data: "full terminal history..." }
```

**Client Messages:**
```typescript
// Send input
{ event: "type", text: "ls -la", nonewline: boolean }

// Request history
{ event: "load_history" }
```

**Functions:**
```typescript
connectWebSocket(port: number): WebSocket | null
disconnectWebSocket(port: number): void
```

**Connection Lifecycle:**
1. Close existing connection for port (if any)
2. Create new WebSocket
3. On open: set status 'active', request history
4. Wire terminal input → WebSocket send
5. On message: write to terminal
6. On close: set status 'idle'
7. On error: set status 'dead'

---

### Idle Manager

Automatically disconnects WebSocket connections for idle sessions to conserve resources.

**Configuration:**
```typescript
IDLE_TIMEOUT_MS = 10 * 60 * 1000    // 10 minutes
MIN_SESSIONS_FOR_IDLE = 10          // Only activate at 10+ sessions
CHECK_INTERVAL_MS = 60 * 1000       // Check every minute
```

**Behavior:**
- Only activates when 10+ sessions exist
- Never disconnects the focused session
- Skips sessions already 'idle' or 'dead'
- Updates `lastActivity` on user interaction

**Functions:**
```typescript
startIdleManager(): void
stopIdleManager(): void
reconnectIfNeeded(port: number): void
```

---

## Views

### HomeView

Grid view of all sessions with preview terminals.

**Route:** `/`

**Behavior:**
- On mount: sync sessions from daemon
- Display 2-column grid of session cards
- Non-interactive terminal previews (scaled 2x)
- Click card → navigate to session view

**State:**
```typescript
manager = useTerminalManager()
```

### SessionView

Full interactive terminal view for a single session.

**Route:** `/:port` (port must be numeric)

**Props:**
```typescript
port: number  // From route params
```

**Features:**
- Interactive terminal with keyboard input
- Control bar: SIGINT, SIGTERM, SIGKILL, Clear, Paste
- Arrow key buttons for navigation
- Tab bar: session name, port, shell, cwd
- Actions: Close Tab, Kill, Refresh, Home

**Actions:**
```typescript
handleClear(): void          // Clear terminal
handleClose(): void          // Detach and return home
handleKill(): void           // Kill session entirely
handleInterrupt(): void      // Send SIGINT
handleSigterm(): void        // Send SIGTERM
handleSigkill(): void        // Send SIGKILL
handlePaste(): void          // Paste from clipboard
scrollToBottom(): void       // Scroll terminal to bottom
sendViaWs(text): void        // Send text via WebSocket
```

---

## Components

### Sidebar

Session list navigation.

**Features:**
- Create new session button (+)
- Home button
- Session list with status indicators
- Active session highlighting

**Status Colors:**
- `active` → Green (`#4ade80`)
- `idle` → Gray (`#6b7280`)
- `dead` → Red (`#f87171`)

### SessionCard

Preview card for a session in the grid view.

**Size:** 50vw × 50vh

**Features:**
- Scaled terminal preview (2x)
- Status indicator
- Session name, port, shell
- Click to open session view

### TerminalViewport

Container for xterm.js terminal instance.

**Props:**
```typescript
port: number
interactive?: boolean  // Enable input and resize
```

**Behavior:**
- `interactive=true`: ResizeObserver, focus management
- `interactive=false`: Static preview
- Auto-connect WebSocket if not connected
- Debounced resize (100ms)

---

## Routing

```typescript
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/:port(\\d+)',  // Numeric port only
      name: 'session',
      component: SessionView,
      props: true,
    },
  ],
})
```

**Hash History:** Uses `#` URLs for static file serving compatibility.

---

## Clipboard Handling

Custom clipboard handling to prevent browser interference:

**Ctrl+C:**
- If terminal has selection → copy to clipboard, clear selection
- Otherwise → let xterm handle it

**Ctrl+V:**
- Read from clipboard → send via WebSocket
- Block browser's native paste

**Right-click:**
- Paste from clipboard via contextmenu event

**Custom Key Events:**
- `Ctrl+Enter` → Send `\x1b[13;5u`
- `Shift+Enter` → Send `\x1b[13;2u`

---

## Build Configuration

### Vite

```typescript
export default defineConfig({
  plugins: [vue(), vueDevTools(), tailwindcss()],
  resolve: {
    alias: { '@': './src' }
  },
  build: {
    outDir: '../static/manager',
    emptyOutDir: true,
  },
  base: './',  // Relative paths for static serving
})
```

**Output:** Built files go to `static/manager/` for serving by FastAPI.

### TypeScript

- Strict mode enabled
- Path alias: `@` → `src/`
- Separate configs for app, vitest, node, e2e

---

## Testing

### Unit Tests (Vitest)

```bash
pnpm test:unit
```

- Test files: `src/**/*.spec.ts`
- Environment: jsdom
- Coverage: `--coverage` flag available

### E2E Tests (Playwright)

```bash
pnpm test:e2e
```

**Configuration:**
- Browsers: Chromium, Firefox, WebKit
- Base URL: `http://localhost:5173` (dev) or `http://localhost:4173` (preview)
- Timeout: 30s per test
- Retries: 2 on CI

**Test Directory:** `e2e/`

---

## Scripts

| Script | Description |
|--------|-------------|
| `pnpm dev` | Start dev server with hot reload |
| `pnpm build` | Type-check and build for production |
| `pnpm preview` | Preview production build |
| `pnpm test:unit` | Run Vitest unit tests |
| `pnpm test:e2e` | Run Playwright E2E tests |
| `pnpm lint` | Run oxlint + ESLint |
| `pnpm format` | Format with Prettier |

---

## Contracts / Invariants

| Invariant | Description |
|-----------|-------------|
| Single terminal per session | Each port has exactly one xterm instance |
| Buffered writes | Terminal writes use queue to prevent escape sequence splitting |
| WebSocket reconnect | Disconnected sessions reconnect on focus |
| Idle cleanup | 10+ sessions trigger idle disconnection after 10 minutes |
| Resize sync | Terminal resize triggers daemon resize API call |
| Hash routing | Uses hash history for static file compatibility |

---

## Design Decisions

| Decision | Why | Confidence |
|----------|-----|------------|
| Vue 3 + Composition API | Modern, type-safe, better DX | High |
| Pinia over Vuex | Simpler, better TypeScript support | High |
| xterm.js | Industry standard terminal emulator | High |
| WebSocket for terminals | Bidirectional, low latency | High |
| Hash history routing | Works with static file serving | High |
| Buffered writes | Prevents ANSI escape sequence corruption | High |
| Idle disconnection | Resource management for many sessions | Medium |
| Tailwind CSS | Utility-first, rapid development | High |

---

## Implementation Pointers

**Repository:** `manager_web_ui/`

**Entry Point:** `src/main.ts`

**Key Files:**
| File | Purpose |
|------|---------|
| `src/stores/terminalManager.ts` | Core state management |
| `src/lib/daemonApi.ts` | HTTP client |
| `src/lib/websocket.ts` | WebSocket handling |
| `src/views/SessionView.vue` | Main terminal interface |
| `src/components/TerminalViewport.vue` | xterm.js wrapper |

**Related:**
- [arch_api.md](arch_api.md) — WebSocket server implementation
- [arch_daemon.md](arch_daemon.md) — Daemon API

---

## Performance Considerations

| Aspect | Value | Notes |
|--------|-------|-------|
| WebSocket poll interval | 100ms | Server-side output check |
| Resize debounce | 100ms | Prevent resize storms |
| Terminal scrollback | 5000 lines | Memory limit |
| Max terminal size | 256×64 | Prevent overflow |
| Idle timeout | 10 minutes | Resource conservation |
| Idle check interval | 60 seconds | Background cleanup |

---

## Security Considerations

| Aspect | Implementation |
|--------|----------------|
| Same-origin | Assumes daemon is on same machine |
| Token handling | Not implemented (localhost bypass) |
| Clipboard access | Requires user permission |
| WebSocket protocol | Matches page protocol (ws/wss) |

**Note:** Web UI is designed for local use. Remote access requires proper authentication in the daemon.

---

## Browser Compatibility

**Target:** Modern browsers (ES2022+)

**Tested:**
- Chromium (Chrome, Edge, Brave)
- Firefox
- WebKit (Safari)

**Required Features:**
- WebSocket
- Clipboard API
- ResizeObserver
- ES modules
- CSS Grid/Flexbox
