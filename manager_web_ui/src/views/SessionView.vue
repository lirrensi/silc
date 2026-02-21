<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import TerminalViewport from '@/components/TerminalViewport.vue'
import { closeSession } from '@/lib/daemonApi'

const route = useRoute()
const router = useRouter()
const manager = useTerminalManager()

const port = computed(() => parseInt(route.params.port as string, 10))
const session = computed(() => manager.getSession(port.value))

console.log(`[SessionView] Setup for port ${port.value}`)

onMounted(() => {
  console.log(`[SessionView] onMounted, setting focused to ${port.value}`)
  manager.setFocused(port.value)
})

onUnmounted(() => {
  console.log(`[SessionView] onUnmounted, clearing focus`)
  manager.setFocused(null)
})

function handleClose(): void {
  console.log(`[SessionView] handleClose for port ${port.value}`)
  manager.detach(port.value)
  manager.setFocused(null)
  router.push('/')
}

async function handleKill(): Promise<void> {
  console.log(`[SessionView] handleKill for port ${port.value}`)
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
      <div class="flex items-center gap-2">
        <span class="font-mono text-lg">:{{ port }}</span>
        <span class="text-sm text-[#a0a0a0]">{{ session?.shell ?? '' }}</span>
      </div>
      <div class="flex items-center gap-2">
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
