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
    class="session-card relative overflow-hidden cursor-pointer hover:ring-2 hover:ring-[#ff80bf] transition-all bg-[#2d2d2d] rounded-lg"
  >
    <!-- Header -->
    <div class="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-3 py-2 bg-[#252526]/90 backdrop-blur-sm border-b border-[#5e5e62]">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" :class="statusColor(session?.status ?? 'idle')"></div>
        <span class="text-sm font-medium">{{ session?.name ?? 'unnamed' }}</span>
        <span class="font-mono text-sm text-[#a0a0a0]">:{{ port }}</span>
      </div>
      <span class="text-sm text-[#6b7280]">{{ session?.shell ?? '' }}</span>
    </div>

    <!-- Terminal Preview (CSS cover style) -->
    <div class="preview-container">
      <div class="terminal-cover">
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  width: 50vw;
  height: 50vh;
}

.preview-container {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.terminal-cover {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(2);
  width: 100%;
  height: 100%;
  transform-origin: center center;
}

.terminal-cover :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-cover :deep(.xterm-viewport) {
  overflow: hidden !important;
}
</style>
