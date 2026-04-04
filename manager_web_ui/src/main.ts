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

app.mount('#app')

// Start idle manager after Pinia is ready
startIdleManager()
