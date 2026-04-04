<!-- FILE: manager_web_ui/src/components/SessionCard.vue -->
<!-- PURPOSE: Present a clickable session card shell for Home dashboard preview content. -->
<!-- OWNS: Session card chrome, route navigation, and slot framing for Home-only cards. -->
<!-- DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md -->

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

function liveTitle(): string {
  if (!session.value) return '—'
  return session.value.title || '—'
}

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
            <span class="truncate text-sm font-medium text-[var(--color-text-primary)]">{{ session?.name || 'unnamed' }}</span>
          </div>
          <p class="mt-1 text-xs font-mono text-[var(--color-text-muted)]">:{{ port }}</p>
          <p class="mt-0.5 truncate text-xs text-[var(--color-text-muted)]">{{ liveTitle() }}</p>
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
            <span class="truncate text-sm font-medium tracking-[0.02em] text-[var(--color-text-primary)]">{{ session?.name || 'unnamed' }}</span>
            <span class="font-mono text-xs text-[var(--color-text-muted)]">:{{ port }}</span>
          </div>
        </div>
        <div class="absolute left-0 right-0 top-[2.9rem] z-10 px-3 text-[11px] text-[var(--color-text-secondary)]">
          <div class="truncate text-[11px] font-medium text-[var(--color-text-muted)]">{{ liveTitle() }}</div>
        </div>

      <div class="preview-container">
        <div class="terminal-stage">
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
  top: 72px;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  padding: 12px;
  box-sizing: border-box;
}

.terminal-stage {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 0;
  overflow: hidden;
}

.terminal-stage :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-stage :deep(.xterm-viewport) {
  overflow: hidden !important;
}
</style>
