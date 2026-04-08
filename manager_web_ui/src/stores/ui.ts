// FILE: manager_web_ui/src/stores/ui.ts
// PURPOSE: Store global UI preferences and hydrate daemon-owned shared settings for the manager UI.
// OWNS: Shared app chrome presets, persisted UI toggles, and daemon settings fallback state.
// EXPORTS: useUiStore - Pinia store for UI state, settings hydration, and actions.
// DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getSettings, updateSettings } from '@/lib/daemonApi'
import {
  DEFAULT_TERMINAL_DEFAULTS,
  resolveTerminalDefaults,
  type TerminalDefaults,
} from '@/lib/themes'
import {
  DEFAULT_MANAGER_THEME_PRESET,
  DEFAULT_TERMINAL_THEME_PRESET,
  applyManagerThemePreset,
  getDefaultThemePresetForMode,
  getThemePresetMode,
  resolveThemePreset,
  type ThemePresetName,
} from '@/lib/themePresets'
import type { DaemonSettings } from '@/lib/daemonApi'
import type { HomeGridDensity } from '@/lib/homePreview'

const SIDEBAR_STORAGE_KEY = 'silc.sidebarCollapsed'
const SIDEBAR_WIDTH_STORAGE_KEY = 'silc.sidebarWidth'
const HOME_GRID_STORAGE_KEY = 'silc.homeGridDensity'
const DAEMON_SETTINGS_CACHE_KEY = 'silc.daemonSettingsCache'
const MANAGER_THEME_STORAGE_KEY = 'silc.managerThemePreset'
const LEGACY_MANAGER_THEME_STORAGE_KEY = 'silc-manager-theme'
const DEFAULT_SIDEBAR_WIDTH = 320
const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 400

interface AppearanceSettingsDraft {
  managerThemePreset: ThemePresetName
  terminalThemePreset: ThemePresetName
  fontSize: number
  lineHeight: number
}

export const useUiStore = defineStore('ui', () => {
  const managerThemePreset = ref<ThemePresetName>(DEFAULT_MANAGER_THEME_PRESET)
  const terminalThemePreset = ref<ThemePresetName>(DEFAULT_TERMINAL_THEME_PRESET)
  const isMobileNavOpen = ref(false)
  const isSidebarCollapsed = ref(false)
  const sidebarWidth = ref(DEFAULT_SIDEBAR_WIDTH)
  const isThemeReady = ref(false)
  const homeGridDensity = ref<HomeGridDensity>('3x3')
  const terminalDefaults = ref<TerminalDefaults>({ ...DEFAULT_TERMINAL_DEFAULTS })

  const resolvedTheme = computed(() => getThemePresetMode(managerThemePreset.value))

  function persistManagerThemeStorage(): void {
    localStorage.setItem(MANAGER_THEME_STORAGE_KEY, managerThemePreset.value)
    localStorage.setItem(LEGACY_MANAGER_THEME_STORAGE_KEY, resolvedTheme.value)
  }

  function buildDaemonSettingsPayload(): DaemonSettings {
    const managerMode = resolvedTheme.value
    const terminalMode = getThemePresetMode(terminalThemePreset.value)

    return {
      ui: {
        managerTheme: managerThemePreset.value,
        themePreference: managerMode,
      },
      terminal: {
        themePreset: terminalThemePreset.value,
        theme: terminalMode,
        cols: terminalDefaults.value.cols,
        rows: terminalDefaults.value.rows,
        scrollback: terminalDefaults.value.scrollback,
        fontFamily: terminalDefaults.value.fontFamily,
        fontSize: terminalDefaults.value.fontSize,
        lineHeight: terminalDefaults.value.lineHeight,
        cursorBlink: terminalDefaults.value.cursorBlink,
      },
    }
  }

  function persistDaemonSettingsCache(): void {
    localStorage.setItem(DAEMON_SETTINGS_CACHE_KEY, JSON.stringify(buildDaemonSettingsPayload()))
  }

  function applyManagerTheme(): void {
    applyManagerThemePreset(managerThemePreset.value)
  }

  function persistAppearanceState(): void {
    persistManagerThemeStorage()
    persistDaemonSettingsCache()
  }

  function applyAppearanceSettings(update: Partial<AppearanceSettingsDraft>): void {
    const nextTerminalDefaults = { ...terminalDefaults.value }

    if (update.managerThemePreset) {
      managerThemePreset.value = update.managerThemePreset
    }
    if (update.terminalThemePreset) {
      terminalThemePreset.value = update.terminalThemePreset
    }
    if (update.fontSize !== undefined && Number.isFinite(update.fontSize)) {
      nextTerminalDefaults.fontSize = Math.round(update.fontSize)
    }
    if (update.lineHeight !== undefined && Number.isFinite(update.lineHeight)) {
      nextTerminalDefaults.lineHeight = update.lineHeight
    }

    terminalDefaults.value = nextTerminalDefaults
    applyManagerTheme()
  }

  function previewAppearanceSettings(update: Partial<AppearanceSettingsDraft>): void {
    applyAppearanceSettings(update)
  }

  async function syncDaemonSettings(): Promise<void> {
    await updateSettings(buildDaemonSettingsPayload() as Record<string, unknown>)
  }

  function setManagerThemePreset(preset: ThemePresetName): void {
    applyAppearanceSettings({ managerThemePreset: preset })
    persistAppearanceState()
    void syncDaemonSettings().catch(() => undefined)
  }

  function setTerminalThemePreset(preset: ThemePresetName): void {
    applyAppearanceSettings({ terminalThemePreset: preset })
    persistAppearanceState()
    void syncDaemonSettings().catch(() => undefined)
  }

  async function setAppearanceSettings(update: Partial<AppearanceSettingsDraft>): Promise<void> {
    applyAppearanceSettings(update)
    persistAppearanceState()
    await syncDaemonSettings()
  }

  function toggleTheme(): void {
    const nextPreset = getDefaultThemePresetForMode(resolvedTheme.value === 'dark' ? 'light' : 'dark')
    setManagerThemePreset(nextPreset)
  }

  function openMobileNav(): void {
    isMobileNavOpen.value = true
  }

  function closeMobileNav(): void {
    isMobileNavOpen.value = false
  }

  function setSidebarCollapsed(collapsed: boolean): void {
    isSidebarCollapsed.value = collapsed
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isSidebarCollapsed.value))
  }

  function openSidebar(): void {
    setSidebarCollapsed(false)
  }

  function closeSidebar(): void {
    setSidebarCollapsed(true)
  }

  function toggleSidebar(): void {
    setSidebarCollapsed(!isSidebarCollapsed.value)
  }

  function setSidebarWidth(width: number): void {
    const nextWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, Math.round(width)))
    sidebarWidth.value = nextWidth
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth.value))
  }

  function setHomeGridDensity(density: HomeGridDensity): void {
    homeGridDensity.value = density
    localStorage.setItem(HOME_GRID_STORAGE_KEY, homeGridDensity.value)
  }

  function applyStoredThemePreset(savedTheme: string | null): void {
    if (!savedTheme) {
      return
    }

    managerThemePreset.value = resolveThemePreset(savedTheme)
    applyManagerTheme()
    persistManagerThemeStorage()
  }

  function loadSettingsPayload(settings: Partial<DaemonSettings> | null | undefined): void {
    const uiTheme = settings?.ui?.managerTheme ?? settings?.ui?.themePreference
    const terminalTheme = settings?.terminal?.themePreset ?? settings?.terminal?.theme

    managerThemePreset.value = resolveThemePreset(uiTheme)
    terminalThemePreset.value = resolveThemePreset(terminalTheme, DEFAULT_TERMINAL_THEME_PRESET)
    terminalDefaults.value = resolveTerminalDefaults(settings?.terminal)
    applyManagerTheme()
    persistAppearanceState()
  }

  async function loadDaemonSettings(): Promise<void> {
    try {
      const settings = await getSettings()
      loadSettingsPayload(settings)
    } catch {
      const cached = localStorage.getItem(DAEMON_SETTINGS_CACHE_KEY)
      if (!cached) {
        persistManagerThemeStorage()
        return
      }

      try {
        const parsed = JSON.parse(cached) as Partial<DaemonSettings>
        loadSettingsPayload(parsed)
      } catch {
        // Ignore bad cache and keep browser fallback state.
      }
    }
  }

  function initTheme(): void {
    if (isThemeReady.value) {
      applyManagerTheme()
      return
    }

    const savedTheme =
      localStorage.getItem(MANAGER_THEME_STORAGE_KEY) ?? localStorage.getItem(LEGACY_MANAGER_THEME_STORAGE_KEY)
    if (savedTheme) {
      applyStoredThemePreset(savedTheme)
    } else {
      applyManagerTheme()
    }

    isThemeReady.value = true
  }

  const savedSidebar = localStorage.getItem(SIDEBAR_STORAGE_KEY)
  if (savedSidebar === 'true' || savedSidebar === 'false') {
    isSidebarCollapsed.value = savedSidebar === 'true'
  }

  const savedSidebarWidth = localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY)
  if (savedSidebarWidth !== null) {
    const parsedSidebarWidth = Number(savedSidebarWidth)
    if (Number.isFinite(parsedSidebarWidth)) {
      sidebarWidth.value = Math.min(
        MAX_SIDEBAR_WIDTH,
        Math.max(MIN_SIDEBAR_WIDTH, Math.round(parsedSidebarWidth)),
      )
    }
  }

  const savedHomeGridDensity = localStorage.getItem(HOME_GRID_STORAGE_KEY)
  if (savedHomeGridDensity === '2x2' || savedHomeGridDensity === '3x3' || savedHomeGridDensity === '4x4') {
    homeGridDensity.value = savedHomeGridDensity
  }

  return {
    managerThemePreset,
    terminalThemePreset,
    resolvedTheme,
    isMobileNavOpen,
    isSidebarCollapsed,
    sidebarWidth,
    isThemeReady,
    homeGridDensity,
    terminalDefaults,
    previewAppearanceSettings,
    setManagerThemePreset,
    setTerminalThemePreset,
    setAppearanceSettings,
    toggleTheme,
    openMobileNav,
    closeMobileNav,
    openSidebar,
    closeSidebar,
    toggleSidebar,
    setSidebarWidth,
    setHomeGridDensity,
    initTheme,
    loadDaemonSettings,
  }
})
