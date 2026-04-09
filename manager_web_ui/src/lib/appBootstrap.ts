// FILE: manager_web_ui/src/lib/appBootstrap.ts
// PURPOSE: Apply shared Pinia store startup for both manager and session web entrypoints.
// OWNS: Theme hydration, terminal default propagation, and daemon settings bootstrapping.
// EXPORTS: bootstrapSharedClientApp - initialize shared web-app store state.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md

import { watch } from 'vue'
import type { Pinia } from 'pinia'
import { useUiStore } from '@/stores/ui'
import { useTerminalManager } from '@/stores/terminalManager'

export function bootstrapSharedClientApp(pinia: Pinia, options?: { startIdleManager?: boolean }): void {
  const ui = useUiStore(pinia)
  const terminalManager = useTerminalManager(pinia)

  console.info('[SessionWeb] bootstrapSharedClientApp:start', {
    startIdleManager: options?.startIdleManager === true,
  })

  ui.initTheme()
  console.info('[SessionWeb] Theme initialized from local preferences')

  watch(
    () => ui.terminalThemePreset,
    (preset) => {
      console.info('[SessionWeb] Applying terminal theme preset', { preset })
      terminalManager.applyTheme(preset)
    },
    { immediate: true },
  )

  watch(
    () => ui.terminalDefaults,
    (defaults) => {
      console.info('[SessionWeb] Applying terminal defaults', defaults)
      terminalManager.applyTerminalDefaults(defaults)
    },
    { immediate: true },
  )

  console.info('[SessionWeb] Loading daemon-backed UI settings')
  void ui.loadDaemonSettings()

  if (options?.startIdleManager) {
    console.info('[SessionWeb] Starting idle manager for shared app bootstrap')
    void import('@/lib/idleManager').then(({ startIdleManager }) => startIdleManager())
  }
}
