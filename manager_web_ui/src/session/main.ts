// FILE: manager_web_ui/src/session/main.ts
// PURPOSE: Boot the standalone session web build with shared stores and session-page chrome.
// OWNS: Session-app startup wiring, Pinia hydration, and standalone entry mounting.
// EXPORTS: none - browser entrypoint.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import SessionApp from './App.vue'
import '@/assets/main.css'
import { bootstrapSharedClientApp } from '@/lib/appBootstrap'

console.info('[SessionWeb] Booting standalone session app', {
  href: window.location.href,
  protocol: window.location.protocol,
  host: window.location.host,
  pathname: window.location.pathname,
  search: window.location.search,
})

const app = createApp(SessionApp)
const pinia = createPinia()

app.use(pinia)
console.info('[SessionWeb] Pinia installed; bootstrapping shared client app')
bootstrapSharedClientApp(pinia)

console.info('[SessionWeb] Mounting standalone session app to #app')
app.mount('#app')
