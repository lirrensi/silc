import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { THEME_STORAGE_KEY, resolveTheme } from '@/lib/themes'
import type { ResolvedTheme, ThemePreference } from '@/lib/themes'

const SIDEBAR_STORAGE_KEY = 'silc.sidebarCollapsed'

export const useUiStore = defineStore('ui', () => {
  const themePreference = ref<ThemePreference>('system')
  const isMobileNavOpen = ref(false)
  const isSidebarCollapsed = ref(false)
  const isThemeReady = ref(false)
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

  return {
    themePreference,
    resolvedTheme,
    isMobileNavOpen,
    isSidebarCollapsed,
    isThemeReady,
    setTheme,
    toggleTheme,
    openMobileNav,
    closeMobileNav,
    openSidebar,
    closeSidebar,
    toggleSidebar,
    initTheme,
  }
})
