<!-- FILE: manager_web_ui/src/views/HomeView.vue -->
<!-- PURPOSE: Render the Home dashboard with a Home-only grid selector and frozen session previews. -->
<!-- OWNS: Home session grid layout, selector state wiring, and session list reconciliation. -->
<!-- DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md -->

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { HOME_GRID_OPTIONS, getHomeGridSlots } from '@/lib/homePreview'
import { useUiStore } from '@/stores/ui'
import SessionCard from '@/components/SessionCard.vue'
import FrozenTerminalPreview from '@/components/FrozenTerminalPreview.vue'

const manager = useTerminalManager()
const ui = useUiStore()
const surfaceRef = ref<HTMLElement | null>(null)

const visibleSessions = computed(() => manager.sessionList.slice(0, getHomeGridSlots(ui.homeGridDensity)))
const gridColumns = computed(() => {
  switch (ui.homeGridDensity) {
    case '2x2':
      return 2
    case '4x4':
      return 4
    default:
      return 3
  }
})

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${gridColumns.value}, minmax(0, 1fr))`,
}))
</script>

<template>
  <div ref="surfaceRef" class="home-view soft-scrollbar h-full overflow-y-auto px-3 py-3 md:px-5 md:py-4">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div class="toolbar-strip glass-panel overflow-hidden">
        <button
          v-for="option in HOME_GRID_OPTIONS"
          :key="option"
          class="bar-button bar-button-tight text-sm"
          :class="ui.homeGridDensity === option ? 'is-active' : ''"
          :aria-pressed="ui.homeGridDensity === option"
          @click="ui.setHomeGridDensity(option)"
        >
          {{ option }}
        </button>
      </div>
    </div>

    <div v-if="manager.sessionList.length === 0" class="glass-panel border-dashed py-12 text-center text-[var(--color-text-secondary)]">
      No sessions yet. Click "+" to create one.
    </div>

    <div
      v-else
      class="grid gap-4 md:gap-5"
      :style="gridStyle"
    >
      <SessionCard v-for="session in visibleSessions" :key="session.port" :port="session.port">
        <FrozenTerminalPreview :port="session.port" :observer-root="surfaceRef" />
      </SessionCard>
    </div>
  </div>
</template>
