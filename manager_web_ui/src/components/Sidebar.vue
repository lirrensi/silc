<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import { listSessions, createSession } from '@/lib/daemonApi'

const router = useRouter()
const manager = useTerminalManager()

const sessions = computed(() => manager.sessionList)

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    default: return 'bg-[#6b7280]'
  }
}

function selectSession(port: number): void {
  router.push(`/${port}`)
}

async function handleCreateNewSession(): Promise<void> {
  try {
    const data = await createSession()
    // The session will be added when we fetch sessions list
    await fetchSessions()
    router.push(`/${data.port}`)
  } catch (err) {
    console.error('Failed to create session:', err)
  }
}

async function fetchSessions(): Promise<void> {
  try {
    const data = await listSessions()
    // Sync sessions with daemon
    for (const daemonSession of data) {
      if (!manager.getSession(daemonSession.port)) {
        manager.createSession(daemonSession.port, daemonSession.session_id, daemonSession.shell)
      }
    }
  } catch (err) {
    console.error('Failed to fetch sessions:', err)
  }
}

// Fetch on mount
fetchSessions()
</script>

<template>
  <aside class="w-48 bg-[#252526] border-r border-[#5e5e62] flex flex-col h-full">
    <!-- Header -->
    <div class="p-3 border-b border-[#5e5e62]">
      <button
        @click="handleCreateNewSession"
        class="w-full px-3 py-2 bg-[#ff80bf] hover:bg-[#ff99cc] text-black font-medium rounded transition-colors text-sm"
      >
        + New
      </button>
    </div>

    <!-- Session List -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="session in sessions"
        :key="session.port"
        @click="selectSession(session.port)"
        class="flex items-center gap-2 px-3 py-2 hover:bg-[#3d3d3d] cursor-pointer transition-colors"
        :class="{ 'bg-[#3d3d3d]': manager.focusedPort === session.port }"
      >
        <div class="w-2 h-2 rounded-full flex-shrink-0" :class="statusColor(session.status)"></div>
        <span class="font-mono text-sm truncate">:{{ session.port }}</span>
      </div>
    </div>
  </aside>
</template>
