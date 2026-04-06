<script setup lang="ts">
// FILE: manager_web_ui/src/components/TerminalViewport.vue
// PURPOSE: Host a session terminal element and delegate all browser resize scheduling to the terminal manager.
// OWNS: Terminal mount/unmount attachment and viewport-triggered fit scheduling.
// EXPORTS: TerminalViewport - session terminal host component.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { listSessions } from '@/lib/daemonApi'
import { connectWebSocket, requestHistoryFrame } from '@/lib/websocket'
import { useTerminalManager } from '@/stores/terminalManager'

const props = defineProps<{
  port: number
  interactive?: boolean
}>()

const manager = useTerminalManager()
const containerRef = ref<HTMLElement | null>(null)
const session = computed(() => manager.getSession(props.port) ?? null)
const isDormant = computed(() => session.value?.status === 'dormant')
const viewportClass = computed(() => {
  return props.interactive
    ? 'terminal-shell terminal-shell--interactive h-full w-full bg-[var(--color-bg-secondary)] box-border'
    : 'terminal-shell terminal-shell--preview h-full w-full bg-[var(--color-bg-primary)] box-border'
})
const hostClass = computed(() => {
  const restoringClass = session.value?.isRestoring === true ? ' terminal-host--restoring' : ''
  const dormantClass = isDormant.value ? ' terminal-host--dormant' : ''

  return props.interactive
    ? `terminal-host terminal-host--interactive min-h-0 flex-1${restoringClass}${dormantClass}`
    : `terminal-host terminal-host--preview min-h-0 h-full w-full${restoringClass}${dormantClass}`
})

let resizeObserver: ResizeObserver | null = null

function scheduleViewportFit(immediate: boolean, reason: string): void {
  manager.scheduleFit(props.port, {
    immediate,
    propagate: props.interactive === true,
    reason,
  })
}

function handleWindowResize(): void {
  scheduleViewportFit(true, 'window-resize')
}

watch(
  () => session.value?.status,
  (next, previous) => {
    if (next === 'dormant') {
      manager.detach(props.port)
      return
    }

    if (previous === 'dormant' && next && next !== 'dormant') {
      void attachAndConnect()
      scheduleViewportFit(true, 'resurrected')
    }
  },
)

onMounted(() => {
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      scheduleViewportFit(false, 'resize-observer')
    })
    resizeObserver.observe(containerRef.value)
  }

  window.addEventListener('resize', handleWindowResize)

  const session = manager.getSession(props.port)
  if (!session) {
    void fetchAndCreateSession()
    return
  }

  if (session.status === 'dormant') {
    return
  }

  void attachAndConnect()
  scheduleViewportFit(true, 'mounted')
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', handleWindowResize)
  manager.detach(props.port)
})

watch(() => props.port, (newPort, oldPort) => {
  if (oldPort) {
    manager.detach(oldPort)
  }

  const currentSession = manager.getSession(newPort)
  if (currentSession?.status === 'dormant') {
    return
  }

  void attachAndConnect()
  manager.scheduleFit(newPort, {
    immediate: true,
    propagate: props.interactive === true,
    reason: 'port-watch',
  })
})

async function fetchAndCreateSession(): Promise<void> {
  try {
    const sessions = await listSessions()
    manager.reconcileSessions(sessions)
    const daemonSession = sessions.find((s) => s.port === props.port)

    if (daemonSession && !daemonSession.dormant) {
      void attachAndConnect()
      scheduleViewportFit(true, 'mounted')
    }
  } catch (err) {
    console.error('[TerminalViewport] Failed to fetch session:', err)
  }
}

async function attachAndConnect(): Promise<void> {
  if (!containerRef.value) return

  const currentSession = manager.getSession(props.port)
  if (!currentSession) return

  if (currentSession.status === 'dormant') return

  await manager.attach(props.port, containerRef.value, {
    propagate: props.interactive === true,
  })

  await manager.applyMeasuredFit(props.port, {
    propagate: props.interactive === true,
    force: true,
    reason: 'takeover-preconnect',
  })

  const ws = connectWebSocket(props.port, { force: true })
  if (ws && ws.readyState === WebSocket.OPEN) {
    requestHistoryFrame(ws)
  }

  if (props.interactive) {
    manager.setFocused(props.port)
  }
}
</script>

<template>
  <div :class="viewportClass">
    <div ref="containerRef" :class="hostClass"></div>
    <div
      v-if="isDormant"
      class="terminal-dormant-overlay pointer-events-none absolute inset-0 flex items-center justify-center px-4 text-center"
    >
      <div class="glass-panel flex max-w-sm flex-col gap-2 p-4">
        <p class="text-sm font-medium text-[var(--color-text-primary)]">Sleeping session</p>
        <p class="text-xs text-[var(--color-text-secondary)]">This session stays dormant until resurrected.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.terminal-shell {
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.terminal-shell--interactive {
  display: flex;
  flex-direction: column;
  padding: 2px 4px 8px;
}

.terminal-shell--preview {
  padding: 0.5rem;
}

.terminal-host {
  min-height: 0;
  overflow: hidden;
}

.terminal-host--restoring {
  opacity: 0;
  pointer-events: none;
}

.terminal-host--dormant {
  opacity: 0.35;
  filter: grayscale(1);
}

.terminal-dormant-overlay {
  background: color-mix(in srgb, var(--color-bg-primary) 78%, transparent);
}

.terminal-shell :deep(.xterm),
.terminal-shell :deep(.xterm-viewport) {
  height: 100%;
}

.terminal-host--interactive :deep(.xterm),
.terminal-host--interactive :deep(.xterm-viewport),
.terminal-host--interactive :deep(.xterm-screen),
.terminal-host--interactive :deep(.xterm-helpers) {
  background: var(--color-bg-secondary);
}
</style>
