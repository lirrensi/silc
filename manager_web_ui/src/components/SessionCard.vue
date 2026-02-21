<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'

const props = defineProps<{
  port: number
}>()

const router = useRouter()
const manager = useTerminalManager()

const session = computed(() => manager.getSession(props.port))

function handleClick(): void {
  router.push(`/${props.port}`)
}

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    default: return 'bg-[#6b7280]'
  }
}
</script>

<template>
  <div
    @click="handleClick"
    class="session-card bg-[#2d2d2d] rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-[#ff80bf] transition-all"
  >
    <!-- Header -->
    <div class="flex items-center justify-between px-2 py-1 bg-[#252526] border-b border-[#5e5e62]">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" :class="statusColor(session?.status ?? 'idle')"></div>
        <span class="text-xs font-medium">{{ session?.name ?? 'unnamed' }}</span>
        <span class="font-mono text-xs text-[#a0a0a0]">:{{ port }}</span>
      </div>
      <span class="text-xs text-[#6b7280]">{{ session?.shell ?? '' }}</span>
    </div>

    <!-- Terminal Preview (scaled down) -->
    <div class="preview-container h-32 overflow-hidden">
      <div class="terminal-wrapper transform scale-[0.25] origin-top-left w-[400%] h-[400%]">
        <!-- TerminalViewport will be inserted here via slot or directly -->
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  min-width: 200px;
}

.preview-container {
  position: relative;
}

.terminal-wrapper {
  position: absolute;
  top: 0;
  left: 0;
}
</style>
