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
    const sessions = await listSessions()
    const daemonSession = sessions.find((s) => s.port === props.port)

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
