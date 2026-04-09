import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'

export function createWebUiConfig(mode: string) {
  const isSessionBuild = mode === 'web'

  return {
    plugins: [
      vue(),
      vueDevTools(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    root: isSessionBuild ? fileURLToPath(new URL('./web', import.meta.url)) : fileURLToPath(new URL('./', import.meta.url)),
    build: {
      outDir: isSessionBuild ? '../../static/web' : '../static/manager',
      emptyOutDir: true,
    },
    base: './',
  }
}

export default defineConfig(({ mode }) => createWebUiConfig(mode))
