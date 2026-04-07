// FILE: manager_web_ui/src/__tests__/uiSettings.spec.ts
// PURPOSE: Verify daemon settings hydration, browser fallback, and theme write-through behavior.
// OWNS: UI store settings loading and local fallback coverage.
// DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_TERMINAL_DEFAULTS } from '@/lib/themes'

const mockGetSettings = vi.hoisted(() => vi.fn())
const mockUpdateSettings = vi.hoisted(() => vi.fn())

vi.mock('@/lib/daemonApi', () => ({
  getSettings: mockGetSettings,
  updateSettings: mockUpdateSettings,
}))

import { useUiStore } from '../stores/ui'

describe('useUiStore daemon settings', () => {
  beforeEach(() => {
    localStorage.clear()
    mockGetSettings.mockReset()
    mockUpdateSettings.mockReset()
    setActivePinia(createPinia())
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: '',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  it('hydrates theme and terminal defaults from the daemon', async () => {
    mockGetSettings.mockResolvedValue({
      ui: { themePreference: 'dark' },
      terminal: {
        theme: 'light',
        cols: 132,
        rows: 40,
        scrollback: 9000,
        fontFamily: 'Fira Code',
        fontSize: 18,
        lineHeight: 1.2,
        cursorBlink: false,
      },
    })

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    expect(ui.themePreference).toBe('dark')
    expect(ui.resolvedTheme).toBe('dark')
    expect(ui.terminalDefaults).toMatchObject({
      theme: 'light',
      cols: 132,
      rows: 40,
      scrollback: 9000,
      fontFamily: 'Fira Code',
      fontSize: 18,
      lineHeight: 1.2,
      cursorBlink: false,
    })
  })

  it('keeps browser theme fallback when the daemon is offline', async () => {
    localStorage.setItem('silc-manager-theme', 'light')
    mockGetSettings.mockRejectedValue(new Error('offline'))

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    expect(ui.resolvedTheme).toBe('light')
    expect(ui.terminalDefaults).toMatchObject(DEFAULT_TERMINAL_DEFAULTS)
  })

  it('writes theme updates back to the daemon', async () => {
    mockGetSettings.mockResolvedValue({ ui: { themePreference: 'system' }, terminal: {} })
    mockUpdateSettings.mockResolvedValue({})

    const ui = useUiStore()
    ui.initTheme()
    ui.setTheme('dark')

    await Promise.resolve()
    await Promise.resolve()

    expect(mockUpdateSettings).toHaveBeenCalledWith({ ui: { themePreference: 'dark' } })
    expect(localStorage.getItem('silc-manager-theme')).toBe('dark')
  })
})
