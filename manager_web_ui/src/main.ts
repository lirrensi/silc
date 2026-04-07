// FILE: manager_web_ui/src/main.ts
// PURPOSE: Bootstrap the Vue app and hydrate shared UI/terminal defaults at startup.
// OWNS: Client app startup wiring and early settings hydration.
// DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md

import { createApp } from 'vue'
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
terminalManager.applyTheme(ui.resolvedTheme)
terminalManager.applyTerminalDefaults(ui.terminalDefaults)

void ui.loadDaemonSettings().then(() => {
  terminalManager.applyTheme(ui.resolvedTheme)
  terminalManager.applyTerminalDefaults(ui.terminalDefaults)
})

app.mount('#app')

// Start idle manager after Pinia is ready
startIdleManager()
