<script setup lang="ts">
// FILE: manager_web_ui/src/components/TerminalViewport.vue
// PURPOSE: Host a session terminal element and delegate all browser resize scheduling to the terminal manager.
// OWNS: Terminal mount/unmount attachment and viewport-triggered fit scheduling.
// EXPORTS: TerminalViewport - session terminal host component.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { listSessions } from '@/lib/daemonApi'
import { connectWebSocket } from '@/lib/websocket'
import { useTerminalManager } from '@/stores/terminalManager'

const props = defineProps<{
  port: number
  interactive?: boolean
}>()

const manager = useTerminalManager()
const containerRef = ref<HTMLElement | null>(null)
const viewportClass = computed(() => {
  return props.interactive
    ? 'terminal-shell terminal-shell--interactive h-full w-full bg-[var(--color-bg-secondary)] box-border'
    : 'terminal-shell terminal-shell--preview h-full w-full bg-[var(--color-bg-primary)] box-border'
})
const hostClass = computed(() => {
  return props.interactive
    ? 'terminal-host terminal-host--interactive min-h-0 flex-1'
    : 'terminal-host terminal-host--preview min-h-0 h-full w-full'
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

  attachAndConnect()
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
  attachAndConnect()
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

    if (daemonSession) {
      attachAndConnect()
      scheduleViewportFit(true, 'mounted')
    }
  } catch (err) {
    console.error('[TerminalViewport] Failed to fetch session:', err)
  }
}

function attachAndConnect(): void {
  if (!containerRef.value) return

  const session = manager.getSession(props.port)
  if (!session) return

  manager.attach(props.port, containerRef.value, {
    propagate: props.interactive === true,
  })

  if (!session.ws || session.ws.readyState !== WebSocket.OPEN) {
    connectWebSocket(props.port)
  }

  if (props.interactive) {
    manager.setFocused(props.port)
  }
}
</script>

<template>
  <div :class="viewportClass">
    <div ref="containerRef" :class="hostClass"></div>
  </div>
</template>

<style scoped>
.terminal-shell {
  min-height: 0;
  overflow: hidden;
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
