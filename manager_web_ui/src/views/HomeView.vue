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

    for (const ds of daemonSessions) {
      let session = manager.getSession(ds.port)
      if (!session) {
        session = manager.createSession(ds.port, ds.session_id, ds.shell, ds.name, ds.cwd)
      }
      if (!session.ws || session.ws.readyState !== WebSocket.OPEN) {
        connectWebSocket(ds.port)
      }
    }
  } catch (err) {
    console.error('[HomeView] Failed to sync sessions:', err)
  }
}
</script>

<template>
  <div class="home-view h-full overflow-y-auto p-4">
    <h1 class="text-2xl font-bold text-[#ff80bf] mb-4">Sessions</h1>

    <div v-if="manager.sessionList.length === 0" class="text-[#a0a0a0] text-center py-8">
      No active sessions. Click "+" to create one.
    </div>

    <div v-else class="grid grid-cols-2 gap-4">
      <SessionCard v-for="session in manager.sessionList" :key="session.port" :port="session.port">
        <TerminalViewport :port="session.port" :interactive="false" />
      </SessionCard>
    </div>
  </div>
</template>
