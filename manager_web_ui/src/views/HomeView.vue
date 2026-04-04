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
    manager.reconcileSessions(daemonSessions)

    for (const ds of daemonSessions) {
      const session = manager.getSession(ds.port)
      if (!session) {
        continue
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
  <div class="home-view soft-scrollbar h-full overflow-y-auto px-3 py-3 md:px-5 md:py-4">
    <div v-if="manager.sessionList.length === 0" class="glass-panel border-dashed py-12 text-center text-[var(--color-text-secondary)]">
      No active sessions. Click "+" to create one.
    </div>

    <div
      v-else
      class="grid gap-4 md:gap-5 [grid-template-columns:repeat(auto-fit,minmax(270px,1fr))] xl:[grid-template-columns:repeat(auto-fit,minmax(320px,1fr))] 2xl:[grid-template-columns:repeat(auto-fit,minmax(360px,1fr))]"
    >
      <SessionCard v-for="session in manager.sessionList" :key="session.port" :port="session.port">
        <TerminalViewport :port="session.port" :interactive="false" />
      </SessionCard>
    </div>
  </div>
</template>
