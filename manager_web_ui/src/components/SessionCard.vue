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
    case 'connecting': return 'bg-[#fbbf24]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    case 'restarting': return 'bg-[#0ea5e9]'
    default: return 'bg-[#6b7280]'
  }
}
</script>

<template>
  <div @click="handleClick" class="cursor-pointer">
    <div class="glass-panel p-3 transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--color-border-strong)] md:hidden">
      <div class="flex items-start gap-2.5">
        <div class="mt-1 h-2.5 w-2.5" :class="statusColor(session?.status ?? 'idle')"></div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="truncate font-medium text-[var(--color-text-primary)]">{{ session?.name ?? 'unnamed' }}</span>
            <span class="border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
              {{ session?.shell ?? '' }}
            </span>
          </div>
          <p class="mt-1 text-xs font-mono text-[var(--color-text-muted)]">:{{ port }}</p>
          <p class="mt-2 truncate text-sm text-[var(--color-text-secondary)]">{{ session?.cwd || 'Home directory' }}</p>
        </div>
      </div>
    </div>

    <div
      class="session-card group relative hidden overflow-hidden border border-[var(--color-border)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-bg-tertiary)_92%,transparent),color-mix(in_srgb,var(--color-bg-primary)_96%,transparent))] shadow-[0_12px_32px_var(--color-shadow)] transition-all duration-200 hover:-translate-y-1 hover:border-[var(--color-accent)]/50 hover:shadow-[0_18px_40px_var(--color-shadow)] hover:ring-1 hover:ring-[var(--color-accent)]/20 md:block"
    >
      <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,var(--color-accent-muted),transparent_36%)]"></div>
      <div class="absolute left-0 right-0 top-0 z-10 flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2 backdrop-blur-sm">
        <div class="min-w-0 flex items-center gap-2">
          <div class="h-2 w-2" :class="statusColor(session?.status ?? 'idle')"></div>
          <span class="truncate text-sm font-medium tracking-[0.02em] text-[var(--color-text-primary)]">{{ session?.name ?? 'unnamed' }}</span>
          <span class="font-mono text-xs text-[var(--color-text-muted)]">:{{ port }}</span>
        </div>
        <span class="border border-[var(--color-border)] px-1.5 py-0.5 text-xs uppercase tracking-[0.16em] text-[var(--color-text-muted)]">{{ session?.shell ?? '' }}</span>
      </div>

      <div class="preview-container">
        <div class="terminal-cover">
          <slot></slot>
        </div>
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
  border-radius: 0;
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
