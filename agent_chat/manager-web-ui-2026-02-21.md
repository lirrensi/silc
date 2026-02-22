# Plan: SILC Manager Web UI
_Build a Vue 3 web UI for managing terminal sessions with xterm.js integration, hash routing, and WebSocket lifecycle management._

---

# Checklist
- [x] Step 1: Install dependencies (Tailwind, xterm.js)
- [x] Step 2: Configure Tailwind CSS
- [x] Step 3: Configure Vite build output to static/manager/
- [x] Step 4: Create base layout styles and CSS variables
- [x] Step 5: Create TerminalManager Pinia store
- [x] Step 6: Create Session type definitions
- [x] Step 7: Create Sidebar component
- [x] Step 8: Create TerminalViewport component
- [x] Step 9: Create SessionCard component for grid previews
- [x] Step 10: Create Homepage grid view
- [x] Step 11: Create Single session view
- [x] Step 12: Configure Vue Router with hash mode
- [x] Step 13: Create App layout with sidebar and router-view
- [x] Step 14: Implement daemon API client
- [x] Step 15: Implement WebSocket connection management
- [x] Step 16: Implement idle disconnect logic
- [x] Step 17: Update index.html title and favicon
- [x] Step 18: Build and verify

---

## Context

The project has a fresh Vue 3 + Vite + TypeScript + Pinia + Vue Router setup at `manager_web_ui/`. Currently contains only template scaffolding. The existing `static/manager/index.html` is a vanilla JS implementation that will be replaced. The daemon runs on port 19999 and exposes `/sessions` endpoint. Individual sessions run on ports 20000+.

**Key decisions locked in:**
- Sidebar shows port list only (no previews)
- Homepage grid shows all terminals scaled down via CSS transform
- Only one terminal receives keyboard input at a time (focused)
- All terminals stay connected to WebSocket when rendered
- 10min idle disconnect IF 10+ sessions
- Hash routing: `/#/` for grid, `/#/20000` for single session
- Tab names: port for now (`:20000`), cwd basename later

---

## Prerequisites

- Node.js 20.19.0+ or 22.12.0+ (check via `node --version`)
- pnpm installed (check via `pnpm --version`)
- `manager_web_ui/node_modules/` exists (run `pnpm install` in `manager_web_ui/` if missing)
- Daemon running on port 19999 for testing (run `silc start` from project root)

---

## Scope Boundaries

**OUT OF SCOPE:**
- `silc/` Python package (no changes to backend)
- `static/web/` (single-session terminal, untouched)
- `docs/` (no documentation updates in this phase)
- cwd-based tab naming (deferred)
- Power user grid (side-by-side typing, deferred)
- Preview optimization (frozen snapshots, deferred)

---

## Steps

### Step 1: Install dependencies (Tailwind, xterm.js)

From `manager_web_ui/` directory, run:
```bash
pnpm add -D tailwindcss @tailwindcss/vite
pnpm add @xterm/xterm @xterm/addon-fit
```

✅ Success: `package.json` shows `tailwindcss`, `@tailwindcss/vite`, `@xterm/xterm`, `@xterm/addon-fit` in dependencies/devDependencies. `pnpm-lock.yaml` updated.
❌ If failed: Check pnpm is installed. Run `npm install -g pnpm` if needed. Re-run commands.

---

### Step 2: Configure Tailwind CSS

Open `manager_web_ui/vite.config.ts`. Replace entire file content with:
```typescript
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
})
```

Create file `manager_web_ui/src/assets/main.css` with content:
```css
@import "tailwindcss";

:root {
  --color-bg-primary: #1e1e1e;
  --color-bg-secondary: #252526;
  --color-bg-tertiary: #2d2d2d;
  --color-bg-hover: #3d3d3d;
  --color-border: #5e5e62;
  --color-text-primary: #ffffff;
  --color-text-secondary: #a0a0a0;
  --color-accent: #ff80bf;
  --color-accent-muted: #ff80bf44;
  --color-success: #4ade80;
  --color-warning: #fbbf24;
  --color-error: #f87171;
  --color-idle: #6b7280;
}

body {
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
```

Open `manager_web_ui/src/main.ts`. Add import after existing imports:
```typescript
import './assets/main.css'
```

✅ Success: `vite.config.ts` includes tailwindcss plugin. `main.css` exists with Tailwind import and CSS variables. `main.ts` imports `main.css`.
❌ If failed: Verify file paths are correct. Check for typos in imports.

---

### Step 3: Configure Vite build output to static/manager/

Open `manager_web_ui/vite.config.ts`. Add `build` configuration inside `defineConfig({ ... })`:
```typescript
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    outDir: '../static/manager',
    emptyOutDir: true,
  },
  base: './',
})
```

✅ Success: `vite.config.ts` has `build.outDir` pointing to `../static/manager` and `base: './'` for relative paths.
❌ If failed: Verify the relative path `../static/manager` resolves correctly from `manager_web_ui/`.

---

### Step 4: Create base layout styles and CSS variables

Create directory `manager_web_ui/src/components/layout/`. This step creates no files (CSS variables already in Step 2), but verify the CSS variables cover needed colors:
- Background layers: primary, secondary, tertiary, hover
- Text: primary, secondary
- Accent (pink theme)
- Status: success (green/active), warning, error (red/dead), idle (grey)

✅ Success: `manager_web_ui/src/assets/main.css` contains all CSS variables listed above.
❌ If failed: Re-read Step 2 output and verify all variables present.

---

### Step 5: Create TerminalManager Pinia store

Create file `manager_web_ui/src/stores/terminalManager.ts`:
```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import type { Session, SessionStatus } from '@/types/session'

export const useTerminalManager = defineStore('terminalManager', () => {
  const sessions = ref<Map<number, Session>>(new Map())
  const focusedPort = ref<number | null>(null)

  // Computed
  const sessionList = computed(() => {
    return Array.from(sessions.value.values()).sort((a, b) => a.port - b.port)
  })

  const focusedSession = computed(() => {
    if (focusedPort.value === null) return null
    return sessions.value.get(focusedPort.value) ?? null
  })

  const activeCount = computed(() => {
    return Array.from(sessions.value.values()).filter(s => s.status === 'active').length
  })

  // Actions
  function createSession(port: number, sessionId: string, shell: string): Session {
    const terminal = new Terminal({
      cols: 120,
      rows: 30,
      scrollback: 5000,
      theme: {
        background: '#1e1e1e',
        foreground: '#ffffff',
        cursor: '#ff80bf',
        selectionBackground: '#ff80bf44',
      },
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 15,
      cursorBlink: true,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    const session: Session = {
      port,
      sessionId,
      shell,
      terminal,
      fitAddon,
      ws: null,
      status: 'idle',
      lastActivity: Date.now(),
    }

    sessions.value.set(port, session)
    return session
  }

  function getSession(port: number): Session | undefined {
    return sessions.value.get(port)
  }

  function removeSession(port: number): void {
    const session = sessions.value.get(port)
    if (session) {
      if (session.ws) {
        session.ws.close()
      }
      session.terminal.dispose()
      sessions.value.delete(port)
    }
  }

  function setFocused(port: number | null): void {
    focusedPort.value = port
    if (port !== null) {
      const session = sessions.value.get(port)
      if (session) {
        session.lastActivity = Date.now()
      }
    }
  }

  function attach(port: number, container: HTMLElement): void {
    const session = sessions.value.get(port)
    if (!session) return

    if (session.terminal.element) {
      session.terminal.element.remove()
    }

    container.appendChild(session.terminal.element)
    session.fitAddon.fit()
  }

  function detach(port: number): void {
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) return

    session.terminal.element.remove()
  }

  function setStatus(port: number, status: SessionStatus): void {
    const session = sessions.value.get(port)
    if (session) {
      session.status = status
    }
  }

  function setWs(port: number, ws: WebSocket | null): void {
    const session = sessions.value.get(port)
    if (session) {
      session.ws = ws
    }
  }

  return {
    sessions,
    focusedPort,
    sessionList,
    focusedSession,
    activeCount,
    createSession,
    getSession,
    removeSession,
    setFocused,
    attach,
    detach,
    setStatus,
    setWs,
  }
})
```

✅ Success: File `manager_web_ui/src/stores/terminalManager.ts` exists with all functions: `createSession`, `getSession`, `removeSession`, `setFocused`, `attach`, `detach`, `setStatus`, `setWs`. Store uses Vue 3 composition API style.
❌ If failed: Check TypeScript imports resolve. Verify `@/types/session` path will exist (created in next step).

---

### Step 6: Create Session type definitions

Create directory `manager_web_ui/src/types/`. Create file `manager_web_ui/src/types/session.ts`:
```typescript
import type { Terminal } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'

export type SessionStatus = 'active' | 'idle' | 'dead'

export interface Session {
  port: number
  sessionId: string
  shell: string
  terminal: Terminal
  fitAddon: FitAddon
  ws: WebSocket | null
  status: SessionStatus
  lastActivity: number
}

export interface DaemonSession {
  port: number
  session_id: string
  shell: string
  idle_seconds: number
  alive: boolean
}
```

✅ Success: File `manager_web_ui/src/types/session.ts` exists with `SessionStatus`, `Session`, and `DaemonSession` types exported.
❌ If failed: Verify directory `manager_web_ui/src/types/` was created.

---

### Step 7: Create Sidebar component

Create file `manager_web_ui/src/components/Sidebar.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'

const router = useRouter()
const manager = useTerminalManager()

const sessions = computed(() => manager.sessionList)

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    default: return 'bg-[#6b7280]'
  }
}

function selectSession(port: number): void {
  router.push(`/${port}`)
}

async function createNewSession(): Promise<void> {
  try {
    const resp = await fetch('http://127.0.0.1:19999/sessions', { method: 'POST' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    // The session will be added when we fetch sessions list
    await fetchSessions()
    router.push(`/${data.port}`)
  } catch (err) {
    console.error('Failed to create session:', err)
  }
}

async function fetchSessions(): Promise<void> {
  try {
    const resp = await fetch('http://127.0.0.1:19999/sessions')
    const data = await resp.json()
    // Sync sessions with daemon
    for (const daemonSession of data) {
      if (!manager.getSession(daemonSession.port)) {
        manager.createSession(daemonSession.port, daemonSession.session_id, daemonSession.shell)
      }
    }
  } catch (err) {
    console.error('Failed to fetch sessions:', err)
  }
}

// Fetch on mount
fetchSessions()
</script>

<template>
  <aside class="w-48 bg-[#252526] border-r border-[#5e5e62] flex flex-col h-full">
    <!-- Header -->
    <div class="p-3 border-b border-[#5e5e62]">
      <button
        @click="createNewSession"
        class="w-full px-3 py-2 bg-[#ff80bf] hover:bg-[#ff99cc] text-black font-medium rounded transition-colors text-sm"
      >
        + New
      </button>
    </div>

    <!-- Session List -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="session in sessions"
        :key="session.port"
        @click="selectSession(session.port)"
        class="flex items-center gap-2 px-3 py-2 hover:bg-[#3d3d3d] cursor-pointer transition-colors"
        :class="{ 'bg-[#3d3d3d]': manager.focusedPort === session.port }"
      >
        <div class="w-2 h-2 rounded-full flex-shrink-0" :class="statusColor(session.status)"></div>
        <span class="font-mono text-sm truncate">:{{ session.port }}</span>
      </div>
    </div>
  </aside>
</template>
```

✅ Success: File `manager_web_ui/src/components/Sidebar.vue` exists. Component shows session list with status dots, "New" button, handles click to route.
❌ If failed: Check Vue imports resolve. Verify `@/stores/terminalManager` path is correct.

---

### Step 8: Create TerminalViewport component

Create file `manager_web_ui/src/components/TerminalViewport.vue`:
```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'

const props = defineProps<{
  port: number
  interactive?: boolean
}>()

const manager = useTerminalManager()
const containerRef = ref<HTMLElement | null>(null)

onMounted(() => {
  const session = manager.getSession(props.port)
  if (!session) {
    // Session doesn't exist in manager, need to fetch from daemon
    fetchAndCreateSession()
    return
  }

  attachAndConnect()
})

onUnmounted(() => {
  manager.detach(props.port)
})

watch(() => props.port, (newPort, oldPort) => {
  if (oldPort) {
    manager.detach(oldPort)
  }
  attachAndConnect()
})

async function fetchAndCreateSession(): Promise<void> {
  try {
    const resp = await fetch('http://127.0.0.1:19999/sessions')
    const sessions = await resp.json()
    const daemonSession = sessions.find((s: { port: number }) => s.port === props.port)

    if (daemonSession) {
      manager.createSession(props.port, daemonSession.session_id, daemonSession.shell)
      attachAndConnect()
    }
  } catch (err) {
    console.error('Failed to fetch session:', err)
  }
}

function attachAndConnect(): void {
  if (!containerRef.value) return

  const session = manager.getSession(props.port)
  if (!session) return

  manager.attach(props.port, containerRef.value)

  // Connect WebSocket if not connected
  if (!session.ws || session.ws.readyState !== WebSocket.OPEN) {
    connectWebSocket(props.port)
  }

  // Set as focused if interactive
  if (props.interactive) {
    manager.setFocused(props.port)
  }
}
</script>

<template>
  <div
    ref="containerRef"
    class="terminal-viewport w-full h-full bg-[#1e1e1e]"
  ></div>
</template>

<style scoped>
.terminal-viewport :deep(.xterm) {
  height: 100%;
}
</style>
```

✅ Success: File `manager_web_ui/src/components/TerminalViewport.vue` exists. Component handles attach/detach on mount/unmount, connects WS if needed.
❌ If failed: Check `@/lib/websocket` path (created in Step 15). For now, create a stub function.

---

### Step 9: Create SessionCard component for grid previews

Create file `manager_web_ui/src/components/SessionCard.vue`:
```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'

const props = defineProps<{
  port: number
}>()

const router = useRouter()
const manager = useTerminalManager()

const session = computed(() => manager.getSession(props.port))

function handleClick(): void {
  router.push(`/${props.port}`)
}

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    default: return 'bg-[#6b7280]'
  }
}
</script>

<template>
  <div
    @click="handleClick"
    class="session-card bg-[#2d2d2d] rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-[#ff80bf] transition-all"
  >
    <!-- Header -->
    <div class="flex items-center justify-between px-2 py-1 bg-[#252526] border-b border-[#5e5e62]">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" :class="statusColor(session?.status ?? 'idle')"></div>
        <span class="font-mono text-xs">:{{ port }}</span>
      </div>
      <span class="text-xs text-[#a0a0a0]">{{ session?.shell ?? '' }}</span>
    </div>

    <!-- Terminal Preview (scaled down) -->
    <div class="preview-container h-32 overflow-hidden">
      <div class="terminal-wrapper transform scale-[0.25] origin-top-left w-[400%] h-[400%]">
        <!-- TerminalViewport will be inserted here via slot or directly -->
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  min-width: 200px;
}

.preview-container {
  position: relative;
}

.terminal-wrapper {
  position: absolute;
  top: 0;
  left: 0;
}
</style>
```

✅ Success: File `manager_web_ui/src/components/SessionCard.vue` exists. Component shows port, status dot, shell type, and scaled terminal preview area.
❌ If failed: Check Vue imports and scoped styles syntax.

---

### Step 10: Create Homepage grid view

Create directory `manager_web_ui/src/views/`. Create file `manager_web_ui/src/views/HomeView.vue`:
```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'
import SessionCard from '@/components/SessionCard.vue'
import TerminalViewport from '@/components/TerminalViewport.vue'

const manager = useTerminalManager()

onMounted(async () => {
  await syncSessions()
})

async function syncSessions(): Promise<void> {
  try {
    const resp = await fetch('http://127.0.0.1:19999/sessions')
    const daemonSessions = await resp.json()

    // Create sessions that don't exist
    for (const ds of daemonSessions) {
      let session = manager.getSession(ds.port)
      if (!session) {
        session = manager.createSession(ds.port, ds.session_id, ds.shell)
      }
      // Connect WebSocket for all sessions
      if (!session.ws || session.ws.readyState !== WebSocket.OPEN) {
        connectWebSocket(ds.port)
      }
    }
  } catch (err) {
    console.error('Failed to sync sessions:', err)
  }
}
</script>

<template>
  <div class="home-view p-4 h-full overflow-y-auto">
    <h1 class="text-2xl font-bold text-[#ff80bf] mb-4">Sessions</h1>

    <div v-if="manager.sessionList.length === 0" class="text-[#a0a0a0] text-center py-8">
      No active sessions. Click "+ New" to create one.
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <SessionCard v-for="session in manager.sessionList" :key="session.port" :port="session.port">
        <TerminalViewport :port="session.port" :interactive="false" />
      </SessionCard>
    </div>
  </div>
</template>
```

✅ Success: File `manager_web_ui/src/views/HomeView.vue` exists. View syncs sessions on mount, renders grid of SessionCards with TerminalViewports inside.
❌ If failed: Verify imports resolve. Check `@/lib/websocket` exists (Step 15).

---

### Step 11: Create Single session view

Create file `manager_web_ui/src/views/SessionView.vue`:
```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import TerminalViewport from '@/components/TerminalViewport.vue'
import { connectWebSocket } from '@/lib/websocket'

const route = useRoute()
const router = useRouter()
const manager = useTerminalManager()

const port = computed(() => parseInt(route.params.port as string, 10))
const session = computed(() => manager.getSession(port.value))

onMounted(() => {
  manager.setFocused(port.value)
})

onUnmounted(() => {
  manager.setFocused(null)
})

function handleClose(): void {
  manager.detach(port.value)
  manager.setFocused(null)
  router.push('/')
}

async function handleKill(): Promise<void> {
  try {
    await fetch(`http://127.0.0.1:19999/sessions/${port.value}`, { method: 'DELETE' })
    manager.removeSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to kill session:', err)
  }
}
</script>

<template>
  <div class="session-view h-full flex flex-col">
    <!-- Tab Bar -->
    <div class="tab-bar flex items-center justify-between px-4 py-2 bg-[#252526] border-b border-[#5e5e62]">
      <div class="flex items-center gap-2">
        <span class="font-mono text-lg">:{{ port }}</span>
        <span class="text-sm text-[#a0a0a0]">{{ session?.shell ?? '' }}</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="handleClose"
          class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          Close Tab
        </button>
        <button
          @click="handleKill"
          class="px-3 py-1 text-sm bg-[#f87171]/20 hover:bg-[#f87171]/40 border border-[#f87171]/50 text-[#f87171] rounded transition-colors"
        >
          Kill
        </button>
      </div>
    </div>

    <!-- Terminal -->
    <div class="flex-1 overflow-hidden">
      <TerminalViewport :port="port" :interactive="true" />
    </div>

    <!-- Control Bar -->
    <div class="control-bar flex items-center gap-2 px-4 py-2 bg-[#252526] border-t border-[#5e5e62]">
      <button
        @click="session?.terminal?.write('\x03')"
        class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
      >
        Ctrl+C
      </button>
      <button
        @click="session?.terminal?.write('\x04')"
        class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
      >
        Ctrl+D
      </button>
      <div class="flex gap-1">
        <button
          @click="session?.terminal?.write('\x1b[A')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ↑
        </button>
        <button
          @click="session?.terminal?.write('\x1b[D')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ←
        </button>
        <button
          @click="session?.terminal?.write('\x1b[B')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ↓
        </button>
        <button
          @click="session?.terminal?.write('\x1b[C')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          →
        </button>
      </div>
    </div>
  </div>
</template>
```

✅ Success: File `manager_web_ui/src/views/SessionView.vue` exists. View shows tab bar with port/shell, terminal viewport, and control bar with Ctrl+C, Ctrl+D, arrow keys.
❌ If failed: Check Vue Router imports. Verify TerminalViewport component path.

---

### Step 12: Configure Vue Router with hash mode

Open `manager_web_ui/src/router/index.ts`. Replace entire file content with:
```typescript
import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/:port(\\d+)',
      name: 'session',
      component: () => import('@/views/SessionView.vue'),
      props: true,
    },
  ],
})

export default router
```

✅ Success: File uses `createWebHashHistory()`. Routes: `/` → HomeView, `/:port` (numeric) → SessionView.
❌ If failed: Check Vue Router v5 syntax (different from v4). Verify `@/views/` paths.

---

### Step 13: Create App layout with sidebar and router-view

Open `manager_web_ui/src/App.vue`. Replace entire file content with:
```vue
<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
</script>

<template>
  <div class="app-layout flex h-screen w-screen overflow-hidden">
    <Sidebar />
    <main class="flex-1 overflow-hidden">
      <router-view />
    </main>
  </div>
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  overflow: hidden;
}
</style>
```

✅ Success: `App.vue` renders Sidebar and router-view side by side. Full viewport height with no scroll on body.
❌ If failed: Check Sidebar component path. Verify Tailwind flex classes work.

---

### Step 14: Implement daemon API client

Create directory `manager_web_ui/src/lib/`. Create file `manager_web_ui/src/lib/daemonApi.ts`:
```typescript
const DAEMON_URL = 'http://127.0.0.1:19999'

export interface DaemonSession {
  port: number
  session_id: string
  shell: string
  idle_seconds: number
  alive: boolean
}

export interface CreateSessionResponse {
  port: number
  session_id: string
  shell: string
}

export async function listSessions(): Promise<DaemonSession[]> {
  const resp = await fetch(`${DAEMON_URL}/sessions`)
  if (!resp.ok) {
    throw new Error(`Failed to list sessions: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function createSession(options?: {
  port?: number
  shell?: string
  cwd?: string
}): Promise<CreateSessionResponse> {
  const resp = await fetch(`${DAEMON_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options ?? {}),
  })
  if (!resp.ok) {
    throw new Error(`Failed to create session: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function closeSession(port: number): Promise<void> {
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}`, { method: 'DELETE' })
  if (!resp.ok) {
    throw new Error(`Failed to close session: HTTP ${resp.status}`)
  }
}
```

✅ Success: File `manager_web_ui/src/lib/daemonApi.ts` exists with `listSessions`, `createSession`, `closeSession` functions.
❌ If failed: Verify fetch API is available in browser context.

---

### Step 15: Implement WebSocket connection management

Create file `manager_web_ui/src/lib/websocket.ts`:
```typescript
import { useTerminalManager } from '@/stores/terminalManager'

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

export function connectWebSocket(port: number): WebSocket | null {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) {
    console.error(`No session found for port ${port}`)
    return null
  }

  // Close existing connection if any
  if (session.ws) {
    session.ws.close()
  }

  const wsUrl = `${WS_PROTOCOL}//127.0.0.1:${port}/ws`
  const ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    manager.setStatus(port, 'active')
    manager.setWs(port, ws)

    // Request terminal history
    ws.send(JSON.stringify({ event: 'load_history' }))
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)

      if (msg.event === 'history' && msg.data) {
        session.terminal.clear()
        session.terminal.write(msg.data)
      } else if (msg.event === 'update' && msg.data) {
        session.terminal.write(msg.data)
      }
    } catch {
      // Raw text output
      session.terminal.write(event.data)
    }
  }

  ws.onclose = () => {
    manager.setStatus(port, 'idle')
    manager.setWs(port, null)
  }

  ws.onerror = (err) => {
    console.error(`WebSocket error for port ${port}:`, err)
    manager.setStatus(port, 'dead')
  }

  // Wire up terminal input to WebSocket
  session.terminal.onData((data: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event: 'type', text: data, nonewline: true }))
    }
  })

  return ws
}

export function disconnectWebSocket(port: number): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (session?.ws) {
    session.ws.close()
    manager.setWs(port, null)
    manager.setStatus(port, 'idle')
  }
}
```

✅ Success: File `manager_web_ui/src/lib/websocket.ts` exists with `connectWebSocket` and `disconnectWebSocket` functions. Handles history load, output updates, terminal input wiring.
❌ If failed: Check Pinia store import. Verify WebSocket API is available.

---

### Step 16: Implement idle disconnect logic

Create file `manager_web_ui/src/lib/idleManager.ts`:
```typescript
import { useTerminalManager } from '@/stores/terminalManager'
import { disconnectWebSocket, connectWebSocket } from './websocket'

const IDLE_TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes
const MIN_SESSIONS_FOR_IDLE = 10
const CHECK_INTERVAL_MS = 60 * 1000 // Check every minute

let checkInterval: ReturnType<typeof setInterval> | null = null

export function startIdleManager(): void {
  if (checkInterval) return

  checkInterval = setInterval(() => {
    const manager = useTerminalManager()
    const sessions = manager.sessionList

    // Only apply idle disconnect if 10+ sessions
    if (sessions.length < MIN_SESSIONS_FOR_IDLE) {
      return
    }

    const now = Date.now()

    for (const session of sessions) {
      // Skip if already disconnected or dead
      if (session.status === 'idle' || session.status === 'dead') {
        continue
      }

      // Skip if this is the focused session
      if (manager.focusedPort === session.port) {
        continue
      }

      // Check if idle for too long
      const idleTime = now - session.lastActivity
      if (idleTime > IDLE_TIMEOUT_MS) {
        console.log(`Disconnecting idle session :${session.port}`)
        disconnectWebSocket(session.port)
      }
    }
  }, CHECK_INTERVAL_MS)
}

export function stopIdleManager(): void {
  if (checkInterval) {
    clearInterval(checkInterval)
    checkInterval = null
  }
}

export function reconnectIfNeeded(port: number): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) return

  // Update activity timestamp
  session.lastActivity = Date.now()

  // Reconnect if idle
  if (session.status === 'idle') {
    connectWebSocket(port)
  }
}
```

Open `manager_web_ui/src/main.ts`. Add idle manager startup:
```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import { startIdleManager } from './lib/idleManager'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

// Start idle manager after Pinia is ready
startIdleManager()
```

✅ Success: File `manager_web_ui/src/lib/idleManager.ts` exists. `main.ts` calls `startIdleManager()` after mount. Logic checks every minute, disconnects WS after 10min idle IF 10+ sessions exist.
❌ If failed: Check that Pinia is initialized before idle manager starts.

---

### Step 17: Update index.html title and favicon

Open `manager_web_ui/index.html`. Replace content with:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🖥️</text></svg>">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SILC Manager</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

✅ Success: Title is "SILC Manager". Favicon is terminal emoji SVG inline.
❌ If failed: Check HTML syntax is valid.

---

### Step 18: Build and verify

From `manager_web_ui/` directory, run:
```bash
pnpm build
```

Verify output:
1. `../static/manager/index.html` exists
2. `../static/manager/assets/` directory contains JS and CSS files
3. No build errors in console

Test in browser:
1. Start daemon: `silc start` from project root
2. Open `static/manager/index.html` in browser (or serve via daemon)
3. Verify sidebar shows sessions
4. Click "+ New" to create session
5. Click session to open single view
6. Type in terminal, verify WebSocket connection
7. Navigate back to home, verify grid shows all sessions

✅ Success: Build completes with exit code 0. `static/manager/` contains built files. Manual testing shows sidebar, grid, single view, and terminal interaction working.
❌ If failed: Check build output for errors. Verify daemon is running on port 19999. Check browser console for JavaScript errors.

---

## Verification

1. **Build succeeds**: `pnpm build` completes with exit 0
2. **Output location**: `static/manager/index.html` and `static/manager/assets/*` exist
3. **Sidebar renders**: Shows session list with status dots
4. **New session**: Clicking "+ New" creates session and routes to it
5. **Terminal renders**: Single session view shows xterm.js terminal
6. **WebSocket works**: Typing in terminal sends data, output appears
7. **Grid view**: Homepage shows all sessions as scaled preview cards
8. **Status indicators**: Active = green, idle = grey, dead = red

---

## Rollback

If build fails or app is broken:
1. Delete `static/manager/` directory
2. Original `static/manager/index.html` is in git history — restore with:
   ```bash
   git checkout HEAD -- static/manager/index.html
   ```
3. Revert `manager_web_ui/` changes:
   ```bash
   git checkout HEAD -- manager_web_ui/
   ```
