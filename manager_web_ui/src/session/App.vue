<script setup lang="ts">
// FILE: manager_web_ui/src/session/App.vue
// PURPOSE: Host the standalone session web surface and expose a QR-friendly session header.
// OWNS: Session-page chrome, URL copy/QR affordances, and session URL handoff behavior.
// EXPORTS: SessionApp - standalone session-page root component.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md, agent_chat/plan_session_end_splash_2026-04-09.md

import { computed, onMounted, ref } from 'vue'
import QRCode from 'qrcode'
import SessionShell from '@/components/SessionShell.vue'

const sessionPort = computed(() => Number.parseInt(window.location.port || '0', 10))
const sessionUrl = computed(() => window.location.href)
const qrDataUrl = ref('')
const showQr = ref(false)

const canRender = computed(() => Number.isFinite(sessionPort.value) && sessionPort.value > 0)

console.info('[SessionWeb] Parsed standalone session location', {
  href: window.location.href,
  sessionPort: sessionPort.value,
  canRender: canRender.value,
})

async function copySessionUrl(): Promise<void> {
  try {
    console.info('[SessionWeb] Copying standalone session URL to clipboard', { url: sessionUrl.value })
    await navigator.clipboard.writeText(sessionUrl.value)
  } catch (err) {
    console.error('[SessionWeb] Failed to copy standalone session URL', err)
  }
}

async function handlePortChange(port: number): Promise<void> {
  const nextUrl = `${window.location.protocol}//${window.location.hostname}:${port}/web${window.location.search}`
  console.info('[SessionWeb] Redirecting standalone session page after port change', {
    previousPort: sessionPort.value,
    nextPort: port,
    nextUrl,
  })
  window.location.assign(nextUrl)
}

onMounted(async () => {
  console.info('[SessionWeb] SessionApp mounted', {
    sessionPort: sessionPort.value,
    canRender: canRender.value,
    showQr: showQr.value,
  })

  if (!canRender.value) {
    console.warn('[SessionWeb] Early render stop: standalone page has no usable session port', {
      rawPort: window.location.port,
    })
    return
  }

  try {
    console.info('[SessionWeb] Generating QR code for standalone session URL')
    qrDataUrl.value = await QRCode.toDataURL(sessionUrl.value, {
      width: 160,
      margin: 1,
      color: {
        dark: '#111111',
        light: '#f5efe4',
      },
    })
    console.info('[SessionWeb] QR code ready for standalone session URL')
  } catch (err) {
    console.error('[SessionWeb] Failed to generate session QR code', err)
  }
})
</script>

<template>
  <div class="flex h-screen w-screen flex-col overflow-hidden bg-[var(--color-bg-primary)] text-[var(--color-text-primary)]">
    <header class="glass-panel m-3 flex items-center justify-between gap-3 px-3 py-2 md:m-4">
      <div class="min-w-0">
        <p class="text-[10px] uppercase tracking-[0.28em] text-[var(--color-text-muted)]">Silc Session</p>
        <p class="truncate text-sm font-medium text-[var(--color-text-primary)]">{{ sessionUrl }}</p>
      </div>
      <div class="toolbar-strip">
        <button class="bar-button text-sm" @click="copySessionUrl">Copy Link</button>
        <button class="bar-button text-sm" @click="showQr = !showQr">{{ showQr ? 'Hide QR' : 'Show QR' }}</button>
      </div>
    </header>

    <div v-if="showQr && qrDataUrl" class="px-3 pb-3 md:px-4">
      <div class="glass-panel inline-flex items-center gap-3 p-3">
        <img :src="qrDataUrl" alt="QR code for this session URL" class="h-32 w-32 border border-[var(--color-border)] bg-white p-2" />
        <div class="min-w-0">
          <p class="text-xs uppercase tracking-[0.24em] text-[var(--color-text-muted)]">Scan to open</p>
          <p class="text-xs text-[var(--color-text-secondary)]">Use another device or mobile browser to open the same session.</p>
        </div>
      </div>
    </div>

    <main class="min-h-0 flex-1 px-2 pb-2 md:px-4 md:pb-4">
      <div v-if="!canRender" class="glass-panel h-full p-4 text-sm text-[var(--color-text-secondary)]">
        Session port unavailable.
      </div>
      <SessionShell v-else :port="sessionPort" surface="standalone" @port-change="handlePortChange" />
    </main>
  </div>
</template>
