<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'
import { listSessions } from '@/lib/daemonApi'

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
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Simple debounce to prevent resize storms
function debouncedFit(port: number): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    manager.fit(port, { propagate: props.interactive === true })
    debounceTimer = null
  }, 100)
}

onMounted(() => {
  // Only set up ResizeObserver for interactive terminals
  if (props.interactive && containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      debouncedFit(props.port)
    })
    resizeObserver.observe(containerRef.value)
  }

  const session = manager.getSession(props.port)
  if (!session) {
    fetchAndCreateSession()
    return
  }

  attachAndConnect()
})

onUnmounted(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
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
    const sessions = await listSessions()
    manager.reconcileSessions(sessions)
    const daemonSession = sessions.find((s) => s.port === props.port)

    if (daemonSession) {
      attachAndConnect()
    }
  } catch (err) {
    console.error('[TerminalViewport] Failed to fetch session:', err)
  }
}

function attachAndConnect(): void {
  if (!containerRef.value) return

  const session = manager.getSession(props.port)
  if (!session) return

  manager.attach(props.port, containerRef.value)

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
    <div v-if="interactive" class="terminal-bottom-gap shrink-0"></div>
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
  padding: 2px 3px 0;
}

.terminal-shell--preview {
  padding: 0.5rem;
}

.terminal-host {
  min-height: 0;
  overflow: hidden;
}

.terminal-bottom-gap {
  height: 10px;
  background: var(--color-bg-secondary);
}

.terminal-shell :deep(.xterm) {
  height: 100%;
}

.terminal-shell :deep(.xterm-viewport) {
  height: 100%;
}

.terminal-host--interactive :deep(.xterm-screen) {
  padding: 1px 2px;
}

.terminal-host--interactive :deep(.xterm),
.terminal-host--interactive :deep(.xterm-viewport),
.terminal-host--interactive :deep(.xterm-screen),
.terminal-host--interactive :deep(.xterm-helpers) {
  background: var(--color-bg-secondary);
}

.terminal-shell :deep(.xterm-screen) {
  padding: 4px;
}
</style>
