// FILE: manager_web_ui/src/main.ts
// PURPOSE: Bootstrap the manager Vue app and hydrate shared UI/terminal defaults at startup.
// OWNS: Manager client startup wiring and early settings hydration.
// DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md, agent_chat/plan_web_manager_settings_cog_2026-04-08.md, agent_chat/plan_web_shell_split_2026-04-09.md

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import { bootstrapSharedClientApp } from '@/lib/appBootstrap'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

bootstrapSharedClientApp(pinia, { startIdleManager: true })

app.mount('#app')
