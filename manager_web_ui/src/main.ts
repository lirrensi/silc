// FILE: manager_web_ui/src/main.ts
// PURPOSE: Bootstrap the Vue app and hydrate shared UI/terminal defaults at startup.
// OWNS: Client app startup wiring and early settings hydration.
// DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md, agent_chat/plan_web_manager_settings_cog_2026-04-08.md

import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import { startIdleManager } from './lib/idleManager'
import { useUiStore } from '@/stores/ui'
import { useTerminalManager } from '@/stores/terminalManager'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

const ui = useUiStore(pinia)
const terminalManager = useTerminalManager(pinia)

ui.initTheme()

watch(
  () => ui.terminalThemePreset,
  (preset) => {
    terminalManager.applyTheme(preset)
  },
  { immediate: true },
)

watch(
  () => ui.terminalDefaults,
  (defaults) => {
    terminalManager.applyTerminalDefaults(defaults)
  },
  { immediate: true },
)

void ui.loadDaemonSettings()

app.mount('#app')

// Start idle manager after Pinia is ready
startIdleManager()
