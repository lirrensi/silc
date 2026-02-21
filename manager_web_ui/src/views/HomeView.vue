<script setup lang="ts">
import { onMounted } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { connectWebSocket } from '@/lib/websocket'
import { listSessions } from '@/lib/daemonApi'
import SessionCard from '@/components/SessionCard.vue'
import TerminalViewport from '@/components/TerminalViewport.vue'

const manager = useTerminalManager()

onMounted(async () => {
  await syncSessions()
})

async function syncSessions(): Promise<void> {
  try {
    const daemonSessions = await listSessions()

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
