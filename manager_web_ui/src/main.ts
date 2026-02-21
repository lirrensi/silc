import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import { startIdleManager } from './lib/idleManager'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

// Start idle manager after Pinia is ready
startIdleManager()
