// FILE: manager_web_ui/src/stores/ui.ts
// PURPOSE: Store global UI preferences including theme, sidebar state, and Home grid density.
// OWNS: Shared app chrome preferences and persisted UI toggles.
// EXPORTS: useUiStore - Pinia store for UI state and actions.
// DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { THEME_STORAGE_KEY, resolveTheme } from '@/lib/themes'
import type { ResolvedTheme, ThemePreference } from '@/lib/themes'
import type { HomeGridDensity } from '@/lib/homePreview'

const SIDEBAR_STORAGE_KEY = 'silc.sidebarCollapsed'
const HOME_GRID_STORAGE_KEY = 'silc.homeGridDensity'

export const useUiStore = defineStore('ui', () => {
  const themePreference = ref<ThemePreference>('system')
  const isMobileNavOpen = ref(false)
  const isSidebarCollapsed = ref(false)
  const isThemeReady = ref(false)
  const homeGridDensity = ref<HomeGridDensity>('3x3')
  let mediaQuery: MediaQueryList | null = null
  let mediaHandler: (() => void) | null = null

  const resolvedTheme = computed<ResolvedTheme>(() => resolveTheme(themePreference.value))

  function applyTheme(): void {
    const theme = resolvedTheme.value
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
  }

  function persistTheme(): void {
    localStorage.setItem(THEME_STORAGE_KEY, themePreference.value)
  }

  function persistSidebar(): void {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isSidebarCollapsed.value))
  }

  function persistHomeGridDensity(): void {
    localStorage.setItem(HOME_GRID_STORAGE_KEY, homeGridDensity.value)
  }

  function setSidebarCollapsed(collapsed: boolean): void {
    isSidebarCollapsed.value = collapsed
    persistSidebar()
  }

  function setTheme(preference: ThemePreference): void {
    themePreference.value = preference
    applyTheme()
    persistTheme()
  }

  function toggleTheme(): void {
    setTheme(resolvedTheme.value === 'dark' ? 'light' : 'dark')
  }

  function openMobileNav(): void {
    isMobileNavOpen.value = true
  }

  function closeMobileNav(): void {
    isMobileNavOpen.value = false
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

  function setHomeGridDensity(density: HomeGridDensity): void {
    homeGridDensity.value = density
    persistHomeGridDensity()
  }

  function initTheme(): void {
    if (isThemeReady.value) {
      applyTheme()
      return
    }

    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY)
    if (savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system') {
      themePreference.value = savedTheme
    }

    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaHandler = () => {
      if (themePreference.value === 'system') {
        applyTheme()
      }
    }
    mediaQuery.addEventListener('change', mediaHandler)

    applyTheme()
    isThemeReady.value = true
  }

  const savedSidebar = localStorage.getItem(SIDEBAR_STORAGE_KEY)
  if (savedSidebar === 'true' || savedSidebar === 'false') {
    isSidebarCollapsed.value = savedSidebar === 'true'
  }

  const savedHomeGridDensity = localStorage.getItem(HOME_GRID_STORAGE_KEY)
  if (savedHomeGridDensity === '2x2' || savedHomeGridDensity === '3x3' || savedHomeGridDensity === '4x4') {
    homeGridDensity.value = savedHomeGridDensity
  }

  return {
    themePreference,
    resolvedTheme,
    isMobileNavOpen,
    isSidebarCollapsed,
    isThemeReady,
    homeGridDensity,
    setTheme,
    toggleTheme,
    openMobileNav,
    closeMobileNav,
    openSidebar,
    closeSidebar,
    toggleSidebar,
    setHomeGridDensity,
    initTheme,
  }
})
