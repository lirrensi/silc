<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'
import { listSessions } from '@/lib/daemonApi'

const props = defineProps<{
  port: number
  interactive?: boolean
}>()

const manager = useTerminalManager()
const containerRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Simple debounce to prevent resize storms
function debouncedFit(port: number): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    manager.fit(port)
    debounceTimer = null
  }, 100)
}

onMounted(() => {
  if (containerRef.value) {
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
    const daemonSession = sessions.find((s) => s.port === props.port)

    if (daemonSession) {
      manager.createSession(props.port, daemonSession.session_id, daemonSession.shell, daemonSession.name, daemonSession.cwd)
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
