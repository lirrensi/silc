<!-- FILE: manager_web_ui/src/components/SidebarSessionRow.vue -->
<!-- PURPOSE: Render one draggable sidebar session row with click, rename, and drop-target behavior. -->
<!-- OWNS: Session row chrome, drag handle wiring, and compact/full row presentation. -->
<!-- EXPORTS: SidebarSessionRow - reusable manager session row. -->
<!-- DOCS: agent_chat/plan_manager_qol_2026-04-05.md -->

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDraggable, useDroppable } from '@dnd-kit/vue'
import type { Session } from '@/types/session'

const props = defineProps<{
  session: Session
  compact?: boolean
  selected?: boolean
}>()

const emit = defineEmits<{
  select: []
  rename: []
}>()

const rootRef = ref<HTMLElement | null>(null)
const handleRef = ref<HTMLElement | null>(null)

const sessionId = computed(() => props.session.port)
const dragData = computed(() => ({ port: props.session.port }))

const { isDragging } = useDraggable({
  id: sessionId,
  element: rootRef,
  handle: handleRef,
  data: dragData,
})

const { isDropTarget } = useDroppable({
  id: sessionId,
  element: rootRef,
  data: dragData,
})

const statusClass = computed(() => {
  switch (props.session.status) {
    case 'active': return 'bg-[#4ade80]'
    case 'connecting': return 'bg-[#86efac] ring-1 ring-[#4ade80]/40'
    case 'idle': return 'bg-[#4ade80]'
    case 'dead': return 'bg-[#f87171]'
    case 'restarting': return 'bg-[#86efac] ring-1 ring-[#4ade80]/40'
    case 'dormant': return 'bg-[#94a3b8] ring-1 ring-[#cbd5e1]/30'
    default: return 'bg-[#4ade80]'
  }
})

const shellLabel = computed(() => props.session.shell || 'shell')
const sessionName = computed(() => props.session.name || 'unnamed')
const sessionTitle = computed(() => props.session.title || '—')
const sessionCwd = computed(() => props.session.cwd || 'Home directory')
const sessionTooltip = computed(() => {
  return [sessionName.value, `:${props.session.port}`, shellLabel.value, sessionCwd.value, sessionTitle.value]
    .filter(Boolean)
    .join(' · ')
})

function handleSelect(): void {
  emit('select')
}

function handleRename(): void {
  emit('rename')
}
</script>

<template>
  <div
    ref="rootRef"
    role="button"
    :tabindex="0"
    @click="handleSelect"
    @dblclick.stop.prevent="handleRename"
    :title="compact ? sessionTooltip : undefined"
    :aria-label="compact ? sessionTooltip : undefined"
    :class="[
      'transition-colors',
      props.session.status === 'dormant' ? 'opacity-70 grayscale' : '',
      compact ? 'mx-auto flex h-9 w-9 items-center justify-center border border-[var(--color-border)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-primary)]' : '',
      isDragging ? 'opacity-60' : '',
      isDropTarget ? 'ring-1 ring-[var(--color-accent)]/40' : '',
      selected
        ? 'bg-[var(--color-accent-muted)]'
        : 'bg-transparent hover:bg-[var(--color-bg-hover)]',
    ]"
  >
    <div
      v-if="!compact"
      class="grid w-full grid-cols-[1.25rem_minmax(0,1fr)] items-start gap-x-2 gap-y-1 border-t border-[var(--color-border)] px-2 py-1.5 text-left"
    >
      <div class="flex flex-col items-center pt-1">
        <button
          ref="handleRef"
          type="button"
          class="flex h-5 w-5 items-center justify-center text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
          title="Move session"
          aria-label="Move session"
          @click.stop
        >
          ⋮⋮
        </button>
        <span class="mt-2 h-2.5 w-2.5 shrink-0" :class="statusClass" aria-hidden="true"></span>
      </div>
      <div class="min-w-0">
        <div class="flex items-baseline justify-between gap-2 text-sm font-medium text-[var(--color-text-primary)]">
          <span class="min-w-0 truncate">{{ sessionName }}</span>
          <span class="shrink-0 font-mono text-[11px] font-normal text-[var(--color-text-muted)]">:{{ session.port }}</span>
        </div>
        <div class="mt-1 flex items-center justify-between gap-2 text-[11px] text-[var(--color-text-secondary)]">
          <span class="min-w-0 truncate">{{ sessionCwd }}</span>
          <span class="shrink-0 uppercase tracking-[0.12em] text-[var(--color-text-muted)]">{{ shellLabel }}</span>
        </div>
        <div class="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{{ sessionTitle }}</div>
      </div>
    </div>

    <div
      v-else
      class="flex h-full w-full items-center justify-center"
    >
      <button
        ref="handleRef"
        type="button"
        class="relative flex h-7 w-7 items-center justify-center"
        title="Drag to reorder"
        aria-label="Drag to reorder"
        @click.stop
      >
        <span class="h-2.5 w-2.5 rounded-full" :class="statusClass"></span>
        <span class="absolute -bottom-2 text-[9px] leading-none text-[var(--color-text-muted)]">{{ props.session.status === 'dormant' ? '☾' : sessionName.slice(0, 1).toUpperCase() }}</span>
      </button>
    </div>
  </div>
</template>
