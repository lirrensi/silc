// FILE: manager_web_ui/src/__tests__/uiSettings.spec.ts
// PURPOSE: Verify daemon settings hydration, browser fallback, and appearance write-through behavior.
// OWNS: UI store settings loading and local fallback coverage.
// DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md

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

  it('hydrates appearance settings from canonical daemon keys', async () => {
    mockGetSettings.mockResolvedValue({
      ui: { managerTheme: 'dracula' },
      terminal: {
        themePreset: 'nord',
        fontSize: 18,
        lineHeight: 1.2,
        cols: 132,
        rows: 40,
        scrollback: 9000,
        fontFamily: 'Fira Code',
      },
    })

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    expect(ui.managerThemePreset).toBe('dracula')
    expect(ui.terminalThemePreset).toBe('nord')
    expect(ui.resolvedTheme).toBe('dark')
    expect(ui.terminalDefaults).toMatchObject({
      cols: 132,
      rows: 40,
      scrollback: 9000,
      fontFamily: 'Fira Code',
      fontSize: 18,
      lineHeight: 1.2,
      cursorBlink: true,
    })
  })

  it('keeps browser fallback when the daemon is offline', async () => {
    localStorage.setItem('silc.managerThemePreset', 'catppuccin')
    mockGetSettings.mockRejectedValue(new Error('offline'))

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    expect(ui.managerThemePreset).toBe('catppuccin')
    expect(ui.resolvedTheme).toBe('dark')
    expect(ui.terminalDefaults).toMatchObject(DEFAULT_TERMINAL_DEFAULTS)
  })

  it('reads legacy keys and writes canonical payloads back to the daemon', async () => {
    mockGetSettings.mockResolvedValue({
      ui: { themePreference: 'dark' },
      terminal: { theme: 'light', fontSize: 17, lineHeight: 1.15 },
    })
    mockUpdateSettings.mockResolvedValue({})

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    expect(ui.managerThemePreset).toBe('amoled')
    expect(ui.terminalThemePreset).toBe('github')

    await ui.setAppearanceSettings({
      managerThemePreset: 'nord',
      terminalThemePreset: 'gruvbox',
      fontSize: 19,
      lineHeight: 1.25,
    })

    expect(mockUpdateSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        ui: {
          managerTheme: 'nord',
          themePreference: 'dark',
        },
        terminal: expect.objectContaining({
          themePreset: 'gruvbox',
          theme: 'dark',
          fontSize: 19,
          lineHeight: 1.25,
        }),
      }),
    )
    expect(localStorage.getItem('silc.managerThemePreset')).toBe('nord')
  })

  it('previews appearance settings without persisting them', async () => {
    mockGetSettings.mockResolvedValue({
      ui: { managerTheme: 'github' },
      terminal: { themePreset: 'amoled', fontSize: 16, lineHeight: 1.1 },
    })

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    ui.previewAppearanceSettings({ managerThemePreset: 'nord', terminalThemePreset: 'gruvbox' })

    expect(ui.managerThemePreset).toBe('nord')
    expect(ui.terminalThemePreset).toBe('gruvbox')
    expect(mockUpdateSettings).not.toHaveBeenCalled()
    expect(localStorage.getItem('silc.managerThemePreset')).toBe('github')
  })

  it('keeps the local appearance update when the daemon write fails', async () => {
    mockGetSettings.mockResolvedValue({
      ui: { managerTheme: 'github' },
      terminal: { themePreset: 'amoled', fontSize: 16, lineHeight: 1.1 },
    })
    mockUpdateSettings.mockRejectedValue(new Error('daemon offline'))

    const ui = useUiStore()
    ui.initTheme()
    await ui.loadDaemonSettings()

    await expect(ui.setAppearanceSettings({
      managerThemePreset: 'nord',
      terminalThemePreset: 'gruvbox',
      fontSize: 19,
      lineHeight: 1.25,
    })).rejects.toThrow('daemon offline')

    expect(ui.managerThemePreset).toBe('nord')
    expect(ui.terminalThemePreset).toBe('gruvbox')
    expect(ui.terminalDefaults.fontSize).toBe(19)
    expect(ui.terminalDefaults.lineHeight).toBe(1.25)
    expect(localStorage.getItem('silc.managerThemePreset')).toBe('nord')
  })
})
