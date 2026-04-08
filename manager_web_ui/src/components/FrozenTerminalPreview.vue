<script setup lang="ts">
// FILE: manager_web_ui/src/components/FrozenTerminalPreview.vue
// PURPOSE: Render a frozen, color-preserving xterm snapshot for Home dashboard cards.
// OWNS: Preview terminal mounting, snapshot refresh, visibility disposal, and local-only fit updates.
// EXPORTS: FrozenTerminalPreview - read-only Home terminal preview host.
// DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md

import { FitAddon } from '@xterm/addon-fit'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import { Terminal } from '@xterm/xterm'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { loadHomePreviewSnapshot } from '@/lib/homePreview'
import { getTerminalThemePreset } from '@/lib/themePresets'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  port: number
  observerRoot: HTMLElement | null
  refreshMs?: number
}>()

const ui = useUiStore()
const hostRef = ref<HTMLElement | null>(null)
const terminalHostRef = ref<HTMLElement | null>(null)
const isVisible = ref(false)

const rootClass = computed(() => [
  'frozen-terminal-preview h-full w-full overflow-hidden pointer-events-none',
  isVisible.value ? 'opacity-100' : 'opacity-0',
])

let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let intersectionObserver: IntersectionObserver | null = null
let resizeObserver: ResizeObserver | null = null
let refreshTimer: number | null = null
let disposed = false

function createTerminal(): void {
  if (terminal || !terminalHostRef.value) {
    return
  }

  terminal = new Terminal({
    cols: 80,
    rows: 24,
    scrollback: 0,
    convertEol: true,
    disableStdin: true,
    allowProposedApi: true,
    cursorBlink: false,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    fontSize: 14,
    lineHeight: 1,
    theme: getTerminalThemePreset(ui.terminalThemePreset),
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.loadAddon(new Unicode11Addon())
  terminal.unicode.activeVersion = '11'
  terminal.open(terminalHostRef.value)
  if (resizeObserver === null) {
    resizeObserver = new ResizeObserver(() => {
      fitTerminal()
    })
    resizeObserver.observe(hostRef.value ?? terminalHostRef.value)
  }
  fitTerminal()
}

function destroyTerminal(): void {
  stopRefreshLoop()
  resizeObserver?.disconnect()
  resizeObserver = null

  try {
    terminal?.dispose()
  } catch {
    // Best-effort cleanup only.
  }

  terminal = null
  fitAddon = null
}

function fitTerminal(): void {
  if (!terminal || !fitAddon || !terminalHostRef.value) {
    return
  }

  try {
    fitAddon.fit()
  } catch {
    // Snapshot preview sizing is best-effort.
  }
}

async function renderSnapshot(): Promise<void> {
  if (!terminal || disposed || !isVisible.value) {
    return
  }

  try {
    const snapshot = await loadHomePreviewSnapshot(props.port)
    if (!terminal || disposed || !isVisible.value) {
      return
    }

    terminal.reset()
    terminal.write(snapshot)
    await nextTick()
    fitTerminal()
  } catch (err) {
    console.error(`[FrozenTerminalPreview] Failed to load snapshot for :${props.port}:`, err)
  }
}

function startRefreshLoop(): void {
  if (refreshTimer !== null) {
    return
  }

  const refreshMs = props.refreshMs ?? 3000
  refreshTimer = window.setInterval(() => {
    void renderSnapshot()
  }, refreshMs)
}

function stopRefreshLoop(): void {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function handleVisibilityChange(visible: boolean): void {
  isVisible.value = visible

  if (visible) {
    createTerminal()
    startRefreshLoop()
    void renderSnapshot()
    return
  }

  destroyTerminal()
}

function observeVisibility(): void {
  if (!hostRef.value) {
    return
  }

  intersectionObserver?.disconnect()
  intersectionObserver = new IntersectionObserver(
    (entries) => {
      handleVisibilityChange(entries.some((entry) => entry.isIntersecting))
    },
    {
      root: props.observerRoot,
      threshold: 0.15,
    },
  )
  intersectionObserver.observe(hostRef.value)
}

onMounted(async () => {
  await nextTick()
  observeVisibility()
})

onUnmounted(() => {
  disposed = true
  intersectionObserver?.disconnect()
  intersectionObserver = null
  destroyTerminal()
})

watch(
  () => ui.terminalThemePreset,
  (theme) => {
    if (terminal) {
      terminal.options.theme = getTerminalThemePreset(theme)
      fitTerminal()
    }
  },
)

watch(
  () => props.observerRoot,
  () => {
    if (hostRef.value) {
      observeVisibility()
    }
  },
)
</script>

<template>
  <div ref="hostRef" :class="rootClass">
    <div ref="terminalHostRef" class="h-full w-full pointer-events-none" />
  </div>
</template>

<style scoped>
.frozen-terminal-preview {
  contain: content;
}
</style>
