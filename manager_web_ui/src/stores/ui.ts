import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { THEME_STORAGE_KEY, resolveTheme } from '@/lib/themes'
import type { ResolvedTheme, ThemePreference } from '@/lib/themes'

export const useUiStore = defineStore('ui', () => {
  const themePreference = ref<ThemePreference>('system')
  const isMobileNavOpen = ref(false)
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

  return {
    themePreference,
    resolvedTheme,
    isMobileNavOpen,
    isThemeReady,
    setTheme,
    toggleTheme,
    openMobileNav,
    closeMobileNav,
    initTheme,
  }
})
