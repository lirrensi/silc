<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import TerminalViewport from '@/components/TerminalViewport.vue'
import { closeSession } from '@/lib/daemonApi'

const route = useRoute()
const router = useRouter()
const manager = useTerminalManager()

const port = computed(() => parseInt(route.params.port as string, 10))
const session = computed(() => manager.getSession(port.value))

onMounted(() => {
  manager.setFocused(port.value)
  refreshTerminal()
})

onUnmounted(() => {
  manager.setFocused(null)
})

// Refresh terminal when switching to this session
watch(port, () => {
  manager.setFocused(port.value)
  refreshTerminal()
})

function refreshTerminal(): void {
  const s = manager.getSession(port.value)
  if (s?.ws && s.ws.readyState === WebSocket.OPEN) {
    s.terminal.clear()
    s.ws.send(JSON.stringify({ event: 'load_history' }))
  }
}

async function handleClear(): Promise<void> {
  const s = manager.getSession(port.value)
  if (s) {
    s.terminal.clear()
    // Send clear to backend
    try {
      await fetch(`http://127.0.0.1:${port.value}/clear`, { method: 'POST' })
    } catch (err) {
      console.error('Clear failed:', err)
    }
  }
}

function handleClose(): void {
  manager.detach(port.value)
  manager.setFocused(null)
  router.push('/')
}

async function handleKill(): Promise<void> {
  try {
    await closeSession(port.value)
    manager.removeSession(port.value)
    router.push('/')
  } catch (err) {
    console.error('Failed to kill session:', err)
  }
}
</script>

<template>
  <div class="session-view h-full flex flex-col">
    <!-- Tab Bar -->
    <div class="tab-bar flex items-center justify-between px-4 py-2 bg-[#252526] border-b border-[#5e5e62]">
      <div class="flex items-center gap-3">
        <span class="font-mono text-lg text-[#ff80bf]">{{ session?.name ?? 'unnamed' }}</span>
        <span class="font-mono text-sm text-[#a0a0a0]">:{{ port }}</span>
        <span class="text-sm text-[#6b7280]">[{{ session?.shell ?? '' }}]</span>
        <span v-if="session?.cwd" class="text-sm text-[#6b7280] truncate max-w-[200px]" :title="session.cwd">{{ session.cwd }}</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="router.push('/')"
          class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
          title="Home"
        >
          🏠
        </button>
        <button
          @click="refreshTerminal"
          class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
          title="Refresh"
        >
          ↻
        </button>
        <button
          @click="handleClose"
          class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          Close Tab
        </button>
        <button
          @click="handleKill"
          class="px-3 py-1 text-sm bg-[#f87171]/20 hover:bg-[#f87171]/40 border border-[#f87171]/50 text-[#f87171] rounded transition-colors"
        >
          Kill
        </button>
      </div>
    </div>

    <!-- Terminal -->
    <div class="flex-1 overflow-hidden">
      <TerminalViewport :port="port" :interactive="true" />
    </div>

    <!-- Control Bar -->
    <div class="control-bar flex items-center gap-2 px-4 py-2 bg-[#252526] border-t border-[#5e5e62]">
      <button
        @click="session?.terminal?.write('\x03')"
        class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
      >
        Ctrl+C
      </button>
      <button
        @click="session?.terminal?.write('\x04')"
        class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
      >
        Ctrl+D
      </button>
      <button
        @click="handleClear"
        class="px-3 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
      >
        Clear
      </button>
      <div class="flex gap-1">
        <button
          @click="session?.terminal?.write('\x1b[A')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ↑
        </button>
        <button
          @click="session?.terminal?.write('\x1b[D')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ←
        </button>
        <button
          @click="session?.terminal?.write('\x1b[B')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          ↓
        </button>
        <button
          @click="session?.terminal?.write('\x1b[C')"
          class="px-2 py-1 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
        >
          →
        </button>
      </div>
    </div>
  </div>
</template>
