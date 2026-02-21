<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'
import { listSessions } from '@/lib/daemonApi'

const props = defineProps<{
  port: number
  interactive?: boolean
}>()

console.log(`[TerminalViewport] Setup for port ${props.port}, interactive=${props.interactive}`)

const manager = useTerminalManager()
const containerRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  console.log(`[TerminalViewport] onMounted for port ${props.port}, containerRef=${containerRef.value ? 'exists' : 'null'}`)

  // Set up ResizeObserver
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      manager.fit(props.port)
    })
    resizeObserver.observe(containerRef.value)
  }

  const session = manager.getSession(props.port)
  if (!session) {
    // Session doesn't exist in manager, need to fetch from daemon
    console.log(`[TerminalViewport] No session in manager, fetching from daemon...`)
    fetchAndCreateSession()
    return
  }

  console.log(`[TerminalViewport] Session found in manager, attaching...`)
  attachAndConnect()
})

onUnmounted(() => {
  console.log(`[TerminalViewport] onUnmounted for port ${props.port}`)
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  manager.detach(props.port)
})

watch(() => props.port, (newPort, oldPort) => {
  console.log(`[TerminalViewport] Port changed from ${oldPort} to ${newPort}`)
  if (oldPort) {
    manager.detach(oldPort)
  }
  attachAndConnect()
})

async function fetchAndCreateSession(): Promise<void> {
  console.log(`[TerminalViewport] fetchAndCreateSession for port ${props.port}`)
  try {
    const sessions = await listSessions()
    console.log(`[TerminalViewport] Fetched ${sessions.length} sessions from daemon`)
    const daemonSession = sessions.find((s) => s.port === props.port)

    if (daemonSession) {
      console.log(`[TerminalViewport] Found daemon session:`, daemonSession)
      manager.createSession(props.port, daemonSession.session_id, daemonSession.shell)
      attachAndConnect()
    } else {
      console.warn(`[TerminalViewport] No daemon session found for port ${props.port}`)
    }
  } catch (err) {
    console.error('[TerminalViewport] Failed to fetch session:', err)
  }
}

function attachAndConnect(): void {
  console.log(`[TerminalViewport] attachAndConnect for port ${props.port}, containerRef=${containerRef.value ? 'exists' : 'null'}`)
  if (!containerRef.value) {
    console.warn(`[TerminalViewport] No containerRef, cannot attach`)
    return
  }

  const session = manager.getSession(props.port)
  if (!session) {
    console.warn(`[TerminalViewport] No session for port ${props.port}`)
    return
  }

  console.log(`[TerminalViewport] Calling manager.attach(${props.port}, container)`)
  manager.attach(props.port, containerRef.value)

  // Connect WebSocket if not connected
  if (!session.ws || session.ws.readyState !== WebSocket.OPEN) {
    console.log(`[TerminalViewport] WebSocket not connected, connecting...`)
    connectWebSocket(props.port)
  } else {
    console.log(`[TerminalViewport] WebSocket already connected (readyState=${session.ws.readyState})`)
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
