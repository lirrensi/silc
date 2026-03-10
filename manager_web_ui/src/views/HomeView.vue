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
  <div class="home-view h-full overflow-y-auto px-5 py-6 md:px-8">
    <div class="mb-6 flex items-end justify-between gap-4 border-b border-[#5e5e62]/70 pb-4">
      <div>
        <p class="mb-1 text-xs uppercase tracking-[0.28em] text-[#a0a0a0]">Manager</p>
        <h1 class="text-3xl font-bold text-[#ff80bf]">Sessions</h1>
      </div>
      <div class="rounded-full border border-[#5e5e62] bg-[#252526]/90 px-4 py-2 text-sm text-[#a0a0a0] shadow-[0_10px_30px_rgba(0,0,0,0.18)]">
        {{ manager.sessionList.length }} live shell{{ manager.sessionList.length === 1 ? '' : 's' }}
      </div>
    </div>

    <div v-if="manager.sessionList.length === 0" class="rounded-2xl border border-dashed border-[#5e5e62] bg-[#252526]/70 py-16 text-center text-[#a0a0a0]">
      No active sessions. Click "+" to create one.
    </div>

    <div
      v-else
      class="grid gap-5 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))] 2xl:[grid-template-columns:repeat(auto-fit,minmax(360px,1fr))]"
    >
      <SessionCard v-for="session in manager.sessionList" :key="session.port" :port="session.port">
        <TerminalViewport :port="session.port" :interactive="false" />
      </SessionCard>
    </div>
  </div>
</template>
