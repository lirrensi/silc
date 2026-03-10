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
    class="session-card group relative overflow-hidden cursor-pointer rounded-2xl border border-[#5e5e62] bg-[linear-gradient(180deg,rgba(45,45,45,0.96),rgba(30,30,30,0.98))] shadow-[0_18px_45px_rgba(0,0,0,0.28)] transition-all duration-200 hover:-translate-y-1 hover:border-[#ff80bf]/60 hover:shadow-[0_24px_55px_rgba(0,0,0,0.38)] hover:ring-1 hover:ring-[#ff80bf]/35"
  >
    <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,128,191,0.12),transparent_36%)]"></div>
    <!-- Header -->
    <div class="absolute top-0 left-0 right-0 z-10 flex items-center justify-between gap-3 border-b border-[#5e5e62] bg-[#252526]/88 px-4 py-3 backdrop-blur-sm">
      <div class="min-w-0 flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" :class="statusColor(session?.status ?? 'idle')"></div>
        <span class="truncate text-sm font-medium tracking-[0.02em]">{{ session?.name ?? 'unnamed' }}</span>
        <span class="font-mono text-xs text-[#a0a0a0]">:{{ port }}</span>
      </div>
      <span class="rounded-full border border-[#5e5e62] px-2 py-0.5 text-xs uppercase tracking-[0.16em] text-[#6b7280]">{{ session?.shell ?? '' }}</span>
    </div>

    <!-- Terminal Preview (CSS cover style) with padding -->
    <div class="preview-container">
      <div class="terminal-cover">
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  width: 100%;
  min-height: 21rem;
  aspect-ratio: 16 / 10;
}

.preview-container {
  position: absolute;
  top: 56px;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  padding: 12px;
  box-sizing: border-box;
}

.terminal-cover {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(1.45);
  width: 100%;
  height: 100%;
  transform-origin: center center;
  border-radius: 14px;
  overflow: hidden;
}

.terminal-cover :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-cover :deep(.xterm-viewport) {
  overflow: hidden !important;
}
</style>
