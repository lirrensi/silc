<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import TerminalViewport from '@/components/TerminalViewport.vue'
import { closeSession, killSession, restartSession, sendSigterm, sendSigkill, sendInterrupt, getSessionHttpUrl, listSessions } from '@/lib/daemonApi'
import { connectWebSocket } from '@/lib/websocket'

const route = useRoute()
const router = useRouter()
const manager = useTerminalManager()
const reconnecting = ref(false)
const showPasteModal = ref(false)
const pasteText = ref('')

const port = computed(() => parseInt(route.params.port as string, 10))
const session = computed(() => manager.getSession(port.value))
const isActive = computed(() => session.value?.status === 'active' && session.value?.ws?.readyState === WebSocket.OPEN)
const isRestarting = computed(() => session.value?.status === 'restarting')
const hasConnectionProblem = computed(() => !isActive.value)
const controlsDisabled = computed(() => !isActive.value)
const disconnectReason = computed(() => session.value?.disconnectReason ?? '')
const connectionLabel = computed(() => {
  if (disconnectReason.value === 'Session claimed by another client') {
    return 'This shell is now controlled from another client.'
  }

  switch (session.value?.status) {
    case 'connecting':
      return 'Connecting to shell websocket...'
    case 'restarting':
      return 'Restarting shell and waiting for PTY to come back...'
    case 'dead':
      return 'Shell websocket is down.'
    case 'idle':
      return 'Shell is disconnected.'
    default:
      return 'Shell is unavailable.'
  }
})

onMounted(() => {
  manager.setFocused(port.value)
  refreshTerminal()
})

onUnmounted(() => {
  manager.setFocused(null)
})

// Refresh terminal when switching to this session
watch(port, () => {
  manager.setFocused(port.value)
  refreshTerminal()
})

function refreshTerminal(): void {
  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN) {
    s.terminal.reset()
    s.ws.send(JSON.stringify({ event: 'load_history' }))
  }
}

async function handleClear(): Promise<void> {
  try {
    await fetch(`${getSessionHttpUrl(port.value)}/clear`, { method: 'POST' })
    refreshTerminal()
  } catch (err) {
    console.error('Clear failed:', err)
  }
}

async function handleClose(): Promise<void> {
  try {
    await closeSession(port.value)
    manager.removeSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to close session:', err)
  }
}

async function handleKill(): Promise<void> {
  try {
    await killSession(port.value)
    manager.removeSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to kill session:', err)
  }
}

async function handleRestart(): Promise<void> {
  if (!session.value || isRestarting.value) {
    return
  }

  try {
    manager.setStatus(port.value, 'restarting')
    const result = await restartSession(port.value)
    await reconnectSession(result.port, true)

    if (result.port !== port.value) {
      router.push(`/${result.port}`)
    }
  } catch (err) {
    manager.setStatus(port.value, 'dead')
    console.error('Failed to restart session:', err)
  }
}

async function waitForSession(portToFind: number, timeoutMs: number = 5000): Promise<boolean> {
  const start = Date.now()

  while (Date.now() - start < timeoutMs) {
    const daemonSessions = await listSessions()
    manager.reconcileSessions(daemonSessions)

    if (daemonSessions.some((daemonSession) => daemonSession.port === portToFind && daemonSession.alive)) {
      return true
    }

    await new Promise((resolve) => window.setTimeout(resolve, 250))
  }

  return false
}

async function reconnectSession(targetPort: number, waitForFreshSession: boolean = false): Promise<void> {
  if (reconnecting.value) {
    return
  }

  reconnecting.value = true

  try {
    if (waitForFreshSession) {
      const ready = await waitForSession(targetPort)
      if (!ready) {
        throw new Error(`Timed out waiting for session :${targetPort}`)
      }
    } else {
      const daemonSessions = await listSessions()
      manager.reconcileSessions(daemonSessions)
    }

    const nextSession = manager.getSession(targetPort)
    if (!nextSession) {
      throw new Error(`Session :${targetPort} is not available`)
    }

    nextSession.terminal.reset()
    connectWebSocket(targetPort, { force: true })
  } finally {
    reconnecting.value = false
  }
}

function sendViaWs(text: string): void {
  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN) {
    s.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
  }
}

async function handleReconnect(): Promise<void> {
  try {
    await reconnectSession(port.value)
  } catch (err) {
    manager.setStatus(port.value, 'dead')
    console.error('Failed to reconnect session:', err)
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

async function handlePaste(): Promise<void> {
  const prefersTouchPaste = window.matchMedia('(pointer: coarse)').matches
  if (prefersTouchPaste) {
    showPasteModal.value = true
    return
  }

  try {
    const text = await navigator.clipboard.readText()
    if (!text) {
      showPasteModal.value = true
      return
    }
    sendViaWs(text)
  } catch {
    showPasteModal.value = true
  }
}

function closePasteModal(): void {
  showPasteModal.value = false
  pasteText.value = ''
}

function submitPasteText(): void {
  if (!pasteText.value) {
    closePasteModal()
    return
  }

  sendViaWs(pasteText.value)
  closePasteModal()
}

function scrollToBottom(): void {
  const s = manager.getSession(port.value)
  if (s?.terminal) {
    s.terminal.scrollToBottom()
  }
}
</script>

<template>
  <div class="session-view h-full flex flex-col">
    <div class="tab-bar flex min-h-[2.4rem] items-stretch justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div class="min-w-0 flex flex-1 items-center gap-2 overflow-hidden px-3 py-1.5 md:px-4">
        <span class="truncate text-sm font-medium text-[var(--color-accent)]">{{ session?.name ?? 'unnamed' }}</span>
        <span class="shrink-0 font-mono text-xs text-[var(--color-text-muted)]">:{{ port }}</span>
        <span class="shrink-0 text-xs text-[var(--color-text-muted)]">[{{ session?.shell ?? '' }}]</span>
        <span v-if="session?.cwd" class="truncate text-xs text-[var(--color-text-secondary)]" :title="session.cwd">
          {{ session.cwd }}
        </span>
      </div>
      <div class="bar-actions shrink-0 border-l border-[var(--color-border)]">
        <button @click="router.push('/')" class="bar-button bar-button-tight text-xs" title="Home">Overview</button>
        <button @click="refreshTerminal" class="bar-button bar-button-tight text-xs" title="Refresh" :disabled="controlsDisabled">Refresh</button>
        <button @click="handleClose" class="bar-button bar-button-tight text-xs">Close Tab</button>
        <button @click="handleKill" class="bar-button bar-button-tight bar-button-danger text-xs">Kill</button>
      </div>
    </div>

    <div class="relative min-h-0 flex-1 overflow-hidden">
      <div :class="hasConnectionProblem ? 'pointer-events-none h-full grayscale opacity-55' : 'h-full'">
        <TerminalViewport :port="port" :interactive="true" />
      </div>
      <div
        v-if="hasConnectionProblem"
        class="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--color-bg-primary)_74%,transparent)] px-4"
      >
        <div class="glass-panel flex w-full max-w-md flex-col gap-3 p-4 text-center">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">{{ connectionLabel }}</p>
          <p v-if="disconnectReason" class="text-xs text-[var(--color-text-secondary)]">{{ disconnectReason }}</p>
          <p class="text-xs text-[var(--color-text-secondary)]">Port `:{{ port }}` is not interactive until the websocket comes back.</p>
          <div class="mx-auto toolbar-strip">
            <button @click="handleReconnect" class="bar-button text-sm" :disabled="reconnecting || isRestarting">
              {{ reconnecting ? 'Reconnecting...' : 'Reconnect' }}
            </button>
            <button @click="handleRestart" class="bar-button bar-button-info text-sm" :disabled="reconnecting || isRestarting">
              {{ isRestarting ? 'Restarting...' : 'Restart' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="control-bar soft-scrollbar shrink-0 overflow-x-auto border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div class="flex min-h-[2.1rem] min-w-max items-stretch">
        <button @click="handleInterrupt" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" title="SIGINT (Ctrl+C) - Interrupt current process" :disabled="controlsDisabled">SIGINT</button>
        <button @click="handleSigterm" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" title="SIGTERM - Graceful termination" :disabled="controlsDisabled">SIGTERM</button>
        <button @click="handleSigkill" class="bar-button bar-button-tight bar-button-danger border-r border-[var(--color-border)] text-xs" title="SIGKILL - Force kill (nuclear option)" :disabled="controlsDisabled">SIGKILL</button>
        <button @click="handleRestart" class="bar-button bar-button-tight bar-button-info border-r border-[var(--color-border)] text-xs" title="Restart session (same port/name/cwd/shell)" :disabled="isRestarting || reconnecting">{{ isRestarting ? 'Restarting' : 'Restart' }}</button>
        <button @click="handleClear" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :disabled="controlsDisabled">Clear</button>
        <button @click="handlePaste" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" title="Paste from clipboard" :disabled="controlsDisabled">Paste</button>
        <button @click="scrollToBottom" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" title="Scroll to bottom" :disabled="controlsDisabled">Bottom</button>
        <button @click="sendViaWs('\x1b[A')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :disabled="controlsDisabled">↑</button>
        <button @click="sendViaWs('\x1b[D')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :disabled="controlsDisabled">←</button>
        <button @click="sendViaWs('\x1b[B')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :disabled="controlsDisabled">↓</button>
        <button @click="sendViaWs('\x1b[C')" class="bar-button bar-button-tight text-xs" :disabled="controlsDisabled">→</button>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="showPasteModal"
        class="fixed inset-0 z-[70] flex items-center justify-center bg-[var(--color-backdrop)] px-4"
        @click.self="closePasteModal"
      >
        <div class="glass-panel flex w-full max-w-lg flex-col gap-3 p-4">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">Paste text into shell</p>
          <textarea
            v-model="pasteText"
            class="min-h-32 w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-accent)]"
            placeholder="Paste command or text here"
            autocapitalize="off"
            autocomplete="off"
            autocorrect="off"
            spellcheck="false"
            @keydown.esc="closePasteModal"
          ></textarea>
          <div class="flex justify-end">
            <div class="toolbar-strip">
              <button @click="closePasteModal" class="bar-button text-sm">Cancel</button>
              <button @click="submitPasteText" class="bar-button bar-button-accent text-sm">Send</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
