<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from '@/components/Sidebar.vue'
import { useUiStore } from '@/stores/ui'
import { useTerminalManager } from '@/stores/terminalManager'

const route = useRoute()
const ui = useUiStore()
const manager = useTerminalManager()

const currentLabel = computed(() => {
  if (route.name === 'session') {
    return manager.focusedSession?.name || `Shell ${route.params.port ?? ''}`
  }

  return 'All Shells'
})

watch(
  () => route.fullPath,
  () => {
    ui.closeMobileNav()
  },
)

watch(
  () => ui.resolvedTheme,
  (theme) => {
    manager.applyTheme(theme)
  },
  { immediate: true },
)
</script>

<template>
  <div class="app-layout flex h-screen w-screen overflow-hidden bg-[var(--color-bg-primary)] text-[var(--color-text-primary)]">
    <div class="pointer-events-none fixed inset-x-0 top-0 z-30 px-4 pt-4 md:hidden">
      <div class="glass-panel pointer-events-auto flex min-h-[2.5rem] items-stretch justify-between overflow-hidden px-0 py-0">
        <div class="bar-actions border-r border-[var(--color-border)]">
          <button class="bar-button px-3 text-sm font-medium" @click="ui.openMobileNav">Shells</button>
        </div>
        <div class="min-w-0 px-4 text-center">
          <p class="text-[10px] uppercase tracking-[0.28em] text-[var(--color-text-muted)]">Silc</p>
          <p class="truncate font-[var(--font-display)] text-base text-[var(--color-text-primary)]">{{ currentLabel }}</p>
        </div>
        <div class="bar-actions border-l border-[var(--color-border)]">
          <button class="bar-button bar-button-accent px-3 text-sm font-medium" @click="ui.toggleTheme">
            {{ ui.resolvedTheme === 'dark' ? 'Light' : 'Dark' }}
          </button>
        </div>
      </div>
    </div>

    <Sidebar />
    <main class="flex-1 overflow-hidden pt-24 md:pt-0">
      <router-view />
    </main>
  </div>
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  overflow: hidden;
}
</style>
