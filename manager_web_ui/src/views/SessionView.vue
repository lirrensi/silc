<script setup lang="ts">
// FILE: manager_web_ui/src/views/SessionView.vue
// PURPOSE: Render an interactive session view with lifecycle controls and terminal recovery actions.
// OWNS: Session-specific terminal controls, reconnect flows, and history refresh orchestration.
// EXPORTS: SessionView - routed interactive session page.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TerminalViewport from '@/components/TerminalViewport.vue'
import {
  closeSession,
  killSession,
  listSessions,
  restartSession,
  sendInterrupt,
  sendSigkill,
  sendSigterm,
} from '@/lib/daemonApi'
import { connectWebSocket, requestHistoryFrame, sendInputFrame } from '@/lib/websocket'
import { useTerminalManager } from '@/stores/terminalManager'

const route = useRoute()
const router = useRouter()
const manager = useTerminalManager()
const reconnecting = ref(false)
const activeOperation = ref<{
  label: string
  stage: string
  detail: string
  tone: 'info' | 'danger' | 'neutral'
} | null>(null)

const port = computed(() => parseInt(route.params.port as string, 10))
const session = computed(() => manager.getSession(port.value))
const isDormant = computed(() => session.value?.status === 'dormant')
const isActive = computed(() => session.value?.status === 'active' && session.value?.ws?.readyState === WebSocket.OPEN)
const isRestarting = computed(() => session.value?.status === 'restarting')
const hasConnectionProblem = computed(() => !isActive.value && !isDormant.value)
const controlsDisabled = computed(() => hasConnectionProblem.value || activeOperation.value !== null)
const disconnectReason = computed(() => session.value?.disconnectReason ?? '')
const sessionBootstrapped = ref(false)

function tip(primary: string, secondary: string): string {
  return `${primary}\n${secondary}`
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function ensureCurrentSessionVisible(): Promise<boolean> {
  try {
    const daemonSessions = await listSessions()
    manager.reconcileSessions(daemonSessions)

    if (!daemonSessions.some((daemonSession) => daemonSession.port === port.value)) {
      sessionBootstrapped.value = false
      manager.removeSession(port.value)
      await router.replace('/')
      return false
    }

    return true
  } catch (err) {
    console.error('Failed to sync session with daemon:', err)
    return true
  }
}

async function bootstrapSession(): Promise<void> {
  try {
    manager.setFocused(port.value)
    sessionBootstrapped.value = false

    const isVisible = await ensureCurrentSessionVisible()
    if (!isVisible) {
      return
    }

    if (session.value?.status === 'dormant') {
      await restartSession(port.value)
      const ready = await waitForSession(port.value)
      if (!ready) {
        return
      }
      const wakeVisible = await ensureCurrentSessionVisible()
      if (!wakeVisible) {
        return
      }
    }

    const interactiveReady = await waitForInteractiveSessionReady(port.value)
    if (!interactiveReady) {
      return
    }

    sessionBootstrapped.value = true
    await refreshTerminal()
  } catch (err) {
    console.error('Failed to bootstrap session:', err)
  }
}

async function ensureInteractiveSessionReady(): Promise<boolean> {
  if (!session.value || session.value.status !== 'dormant') {
    return await waitForInteractiveSessionReady(port.value)
  }

  try {
    await restartSession(port.value)
    const ready = await waitForSession(port.value)
    if (!ready) {
      return false
    }

    const visible = await ensureCurrentSessionVisible()
    if (!visible) {
      return false
    }

    return await waitForInteractiveSessionReady(port.value)
  } catch (err) {
    console.error('Failed to wake dormant session:', err)
    return false
  }
}

async function waitForInteractiveSessionReady(
  targetPort: number,
  timeoutMs: number = 5000,
): Promise<boolean> {
  const start = Date.now()

  while (Date.now() - start < timeoutMs) {
    const currentSession = manager.getSession(targetPort)
    if (
      currentSession
      && currentSession.status !== 'dormant'
      && currentSession.terminal
      && currentSession.ws?.readyState === WebSocket.OPEN
    ) {
      return true
    }

    await new Promise((resolve) => window.setTimeout(resolve, 100))
  }

  return false
}

async function runOperation(
  label: string,
  tone: 'info' | 'danger' | 'neutral',
  steps: Array<{ stage: string; detail: string; run?: () => Promise<void> | void }>,
  minVisibleMs: number = 240,
): Promise<void> {
  const startedAt = performance.now()
  activeOperation.value = {
    label,
    stage: steps[0]?.stage ?? 'Working',
    detail: steps[0]?.detail ?? '',
    tone,
  }

  await nextTick()

  try {
    for (const step of steps) {
      activeOperation.value = {
        label,
        stage: step.stage,
        detail: step.detail,
        tone,
      }
      await nextTick()

      if (step.run) {
        await step.run()
      }
    }

    activeOperation.value = {
      label,
      stage: 'Complete',
      detail: 'The daemon and terminal have finished the requested work.',
      tone,
    }
    await nextTick()

    const elapsed = performance.now() - startedAt
    if (elapsed < minVisibleMs) {
      await sleep(minVisibleMs - elapsed)
    }
  } catch (err) {
    activeOperation.value = {
      label,
      stage: 'Failed',
      detail: err instanceof Error ? err.message : String(err),
      tone: 'danger',
    }
    await nextTick()
    await sleep(1200)
    throw err
  } finally {
    if (activeOperation.value?.label === label) {
      activeOperation.value = null
    }
  }
}
const connectionLabel = computed(() => {
  if (isDormant.value) {
    return 'This session is sleeping on disk until resurrected.'
  }

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
  void bootstrapSession()
})

onUnmounted(() => {
  sessionBootstrapped.value = false
  manager.setFocused(null)
})

watch(session, (next, previous) => {
  if (!sessionBootstrapped.value || previous === undefined || next !== undefined) {
    return
  }

  sessionBootstrapped.value = false
  void router.replace('/')
})

watch(port, () => {
  void bootstrapSession()
})

async function refreshTerminal(): Promise<void> {
  if (isDormant.value) {
    return
  }

  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN && s.terminal) {
    await manager.flushWrites(port.value)
    s.terminal.reset()
    const historyLoaded = manager.waitForHistoryRefresh(port.value)
    requestHistoryFrame(s.ws)
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        manager.resolveHistoryRefresh(port.value)
        reject(new Error('Timed out waiting for refreshed terminal history'))
      }, 5000)

      historyLoaded.then(
        () => {
          window.clearTimeout(timeout)
          resolve()
        },
        (err) => {
          window.clearTimeout(timeout)
          reject(err)
        },
      )
    })
  }
}

async function handleRefresh(): Promise<void> {
  try {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    const isVisible = await ensureCurrentSessionVisible()
    if (!isVisible) {
      return
    }

    await runOperation('Refresh', 'info', [
      {
        stage: 'Requesting backend history',
        detail: 'The daemon buffer is being asked for the current screen state.',
        run: async () => {
          await refreshTerminal()
        },
      },
      {
        stage: 'Refitting viewport',
        detail: 'The terminal viewport is recalculated to match the current browser size.',
        run: async () => {
          manager.refreshTerminalSurface(port.value)
          await nextTick()
        },
      },
      {
        stage: 'Repainting display',
        detail: 'The terminal surface is redrawn after the history and fit settle.',
        run: async () => {
          manager.forceRedraw(port.value)
          await nextTick()
        },
      },
      {
        stage: 'History restored',
        detail: 'The browser terminal now matches the daemon buffer again.',
        run: async () => {
          await nextTick()
        },
      },
    ])
  } catch (err) {
    console.error('Refresh failed:', err)
  }
}

async function handleClose(): Promise<void> {
  const currentPort = port.value

  try {
    await runOperation('Close session', 'neutral', [
      {
        stage: 'Requesting daemon close',
        detail: 'Asking the daemon to stop the session cleanly.',
        run: async () => {
          await closeSession(currentPort)
        },
      },
      {
        stage: 'Updating the UI',
        detail: 'Removing the session locally and returning home.',
        run: async () => {
          manager.removeSession(currentPort)
          await router.push('/')
        },
      },
    ])
  } catch (err) {
    console.error('Failed to close session:', err)
  }
}

async function handleKill(): Promise<void> {
  const currentPort = port.value

  try {
    await runOperation('Kill session', 'danger', [
      {
        stage: 'Requesting daemon kill',
        detail: 'Sending the hard-stop request to the daemon and PTY layer.',
        run: async () => {
          await killSession(currentPort)
        },
      },
      {
        stage: 'Updating the UI',
        detail: 'Removing the dead session locally and returning home.',
        run: async () => {
          manager.removeSession(currentPort)
          await router.push('/')
        },
      },
    ])
  } catch (err) {
    console.error('Failed to kill session:', err)
  }
}

async function handleRestart(): Promise<void> {
  if (isRestarting.value) {
    return
  }

  try {
    await runOperation('Restart session', 'info', [
      {
        stage: 'Stopping the current shell',
        detail: 'The current PTY is being replaced with a fresh shell instance.',
        run: async () => {
          manager.setStatus(port.value, 'restarting')
          const result = await restartSession(port.value)
          await reconnectSession(result.port, true)

          if (result.port !== port.value) {
            await router.push(`/${result.port}`)
          }
        },
      },
      {
        stage: 'Reconnecting to the fresh session',
        detail: 'The browser terminal is waiting for the new websocket to come back.',
        run: async () => {
          await nextTick()
        },
      },
    ], 420)
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
    if (!nextSession || !nextSession.terminal) {
      throw new Error(`Session :${targetPort} is not available`)
    }

    await manager.flushWrites(targetPort)
    nextSession.terminal.reset()
    await manager.applyMeasuredFit(targetPort, {
      propagate: true,
      force: true,
      reason: 'reconnect-preconnect',
    })
    connectWebSocket(targetPort, { force: true })
    manager.refreshTerminalSurface(targetPort)
  } finally {
    reconnecting.value = false
  }
}

function sendViaWs(text: string): void {
  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN) {
    sendInputFrame(s.ws, text)
  }
}

async function handleReconnect(): Promise<void> {
  try {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await reconnectSession(port.value)
  } catch (err) {
    manager.setStatus(port.value, 'dead')
    console.error('Failed to reconnect session:', err)
  }
}

async function handleInterrupt(): Promise<void> {
  if (!(await ensureInteractiveSessionReady())) {
    return
  }

  await runOperation('Send SIGINT', 'info', [
    {
      stage: 'Sending interrupt',
      detail: 'The foreground process group is being asked to stop cleanly.',
      run: async () => {
        await sendInterrupt(port.value)
      },
    },
  ], 160)
}

async function handleSigterm(): Promise<void> {
  if (!(await ensureInteractiveSessionReady())) {
    return
  }

  await runOperation('Send SIGTERM', 'info', [
    {
      stage: 'Sending graceful termination',
      detail: 'The foreground process group is being asked to exit politely.',
      run: async () => {
        await sendSigterm(port.value)
      },
    },
  ])
}

async function handleSigkill(): Promise<void> {
  if (!(await ensureInteractiveSessionReady())) {
    return
  }

  await runOperation('Send SIGKILL', 'danger', [
    {
      stage: 'Sending force kill',
      detail: 'The foreground process group is being terminated immediately.',
      run: async () => {
        await sendSigkill(port.value)
      },
    },
  ])
}

async function handlePaste(): Promise<void> {
  try {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await manager.pasteClipboardText(port.value)
  } catch (err) {
    console.error('Paste failed:', err)
  }
}

function scrollToBottom(): void {
  const s = manager.getSession(port.value)
  if (s?.terminal) {
    s.terminal.scrollToBottom()
  }
}

function handleBottom(): void {
  void (async () => {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    scrollToBottom()
  })()
}

async function refitTerminal(): Promise<void> {
  if (!(await ensureInteractiveSessionReady())) {
    return
  }

  await runOperation('Refit terminal', 'info', [
    {
      stage: 'Measuring the viewport',
      detail: 'The terminal container is being remeasured and resized.',
      run: async () => {
        manager.refreshTerminalSurface(port.value)
        await nextTick()
      },
    },
  ], 180)
}

async function redrawTerminal(): Promise<void> {
  if (!(await ensureInteractiveSessionReady())) {
    return
  }

  await runOperation('Redraw terminal', 'info', [
    {
      stage: 'Repainting the renderer',
      detail: 'The xterm display is being repainted without changing the buffer.',
      run: async () => {
        manager.forceRedraw(port.value)
        await nextTick()
      },
    },
  ], 180)
}

function sendArrowKey(sequence: string): void {
  void (async () => {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    sendViaWs(sequence)
  })()
}
</script>

<template>
  <div class="session-view h-full flex flex-col">
    <div class="tab-bar flex min-h-[2.4rem] items-stretch justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div class="min-w-0 flex flex-1 items-center gap-2 overflow-hidden px-3 py-1.5 md:px-4">
        <span class="truncate text-sm font-medium text-[var(--color-accent)]">{{ session?.name || 'unnamed' }}</span>
        <span class="shrink-0 font-mono text-xs text-[var(--color-text-muted)]">:{{ port }}</span>
        <span class="shrink-0 text-xs text-[var(--color-text-muted)]">[{{ session?.shell ?? '' }}]</span>
        <span v-if="session?.cwd" class="truncate text-xs text-[var(--color-text-secondary)]" :title="session.cwd">
          {{ session.cwd }}
        </span>
        <span class="truncate text-xs text-[var(--color-text-muted)]">{{ session?.title || '—' }}</span>
      </div>
      <div class="bar-actions shrink-0 border-l border-[var(--color-border)]">
        <button
          @click="handleRestart"
          class="bar-button bar-button-tight bar-button-info text-xs"
          :title="tip('Restart the session', 'Recreates the shell and reconnects the browser to it.')"
          :disabled="activeOperation !== null || isRestarting"
        >
          Restart
        </button>
        <button
          @click="handleClose"
          class="bar-button bar-button-tight text-xs"
          :title="tip('Close this session gracefully', 'Asks the daemon to shut the session down and return home.')"
        >
          Close Session
        </button>
        <button
          @click="handleKill"
          class="bar-button bar-button-tight bar-button-danger text-xs"
          :title="tip('Force-kill this session', 'Use when graceful close is not enough or the shell is wedged.')"
        >
          Kill
        </button>
      </div>
    </div>

    <div class="relative min-h-0 flex-1 overflow-hidden">
      <div
        v-if="isDormant"
        class="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--color-bg-primary)_74%,transparent)] px-4"
      >
        <div class="glass-panel flex w-full max-w-md flex-col gap-3 p-4 text-center">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">Waking session</p>
          <p class="text-xs text-[var(--color-text-secondary)]">The session is being materialized before interaction continues.</p>
        </div>
      </div>
      <div :class="hasConnectionProblem ? 'pointer-events-none h-full grayscale opacity-55' : 'h-full'">
        <TerminalViewport :port="port" :interactive="true" />
      </div>
      <div v-if="activeOperation" class="pointer-events-none absolute right-3 top-3 z-20 w-[min(28rem,calc(100%-1.5rem))]">
        <div class="glass-panel pointer-events-auto flex items-center justify-between gap-3 px-3 py-2 shadow-lg">
          <div class="min-w-0">
            <p class="text-[10px] uppercase tracking-[0.3em] text-[var(--color-text-muted)]">Processing</p>
            <p class="truncate text-sm font-medium text-[var(--color-text-primary)]">{{ activeOperation.label }}</p>
            <p class="text-xs text-[var(--color-text-secondary)]">{{ activeOperation.stage }}</p>
            <p class="text-xs text-[var(--color-text-muted)]">{{ activeOperation.detail }}</p>
          </div>
          <div
            class="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full"
            :class="activeOperation.tone === 'danger' ? 'bg-red-400' : 'bg-[var(--color-accent)]'"
          ></div>
        </div>
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
            <button
              @click="handleReconnect"
              class="bar-button text-sm"
              :title="tip('Reconnect to the session', 'Reopens the websocket when the shell is still alive.')"
              :disabled="reconnecting || isRestarting"
            >
              {{ reconnecting ? 'Reconnecting...' : 'Reconnect' }}
            </button>
            <button
              @click="handleRestart"
              class="bar-button bar-button-info text-sm"
              :title="tip('Restart the session', 'Recreates the shell and reconnects the browser to it.')"
              :disabled="reconnecting || isRestarting"
            >
              {{ isRestarting ? 'Restarting...' : 'Restart' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="control-bar soft-scrollbar shrink-0 overflow-x-auto border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div class="flex min-h-[2.1rem] min-w-max items-stretch">
        <div class="flex items-stretch">
          <button @click="handleRefresh" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Refresh the buffer', 'Reloads the current screen state from the daemon history.')" :disabled="controlsDisabled">Refresh</button>
          <button @click="handleBottom" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Jump to the bottom', 'Scrolls the viewport to the newest output line.')" :disabled="controlsDisabled">Bottom</button>
          <button @click="sendArrowKey('\x1b[A')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send Up Arrow', 'Useful for shell history and command-line navigation.')" :disabled="controlsDisabled">↑</button>
          <button @click="sendArrowKey('\x1b[D')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send Left Arrow', 'Moves the cursor one character to the left.')" :disabled="controlsDisabled">←</button>
          <button @click="sendArrowKey('\x1b[B')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send Down Arrow', 'Moves through command history or lists.')" :disabled="controlsDisabled">↓</button>
          <button @click="sendArrowKey('\x1b[C')" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send Right Arrow', 'Moves the cursor one character to the right.')" :disabled="controlsDisabled">→</button>
          <button @click="handlePaste" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Paste from clipboard', 'Reads clipboard text and sends it straight to the shell.')" :disabled="controlsDisabled">Paste</button>
        </div>
        <div class="flex-1"></div>
        <div class="flex items-stretch">
          <button @click="handleInterrupt" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send SIGINT', 'Equivalent to Ctrl+C for the foreground process.')" :disabled="controlsDisabled">SIGINT</button>
          <button @click="handleSigterm" class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs" :title="tip('Send SIGTERM', 'Requests a graceful shutdown from the shell process group.')" :disabled="controlsDisabled">SIGTERM</button>
          <button @click="handleSigkill" class="bar-button bar-button-tight bar-button-danger border-r border-[var(--color-border)] text-xs" :title="tip('Send SIGKILL', 'Forcibly terminates the foreground process immediately.')" :disabled="controlsDisabled">SIGKILL</button>
        </div>
      </div>
    </div>
  </div>
</template>
