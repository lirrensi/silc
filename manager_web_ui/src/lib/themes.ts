// FILE: manager_web_ui/src/lib/themes.ts
// PURPOSE: Define shared theme palettes and terminal default resolution helpers for the manager UI.
// OWNS: Theme preference resolution, xterm theme palettes, and terminal default normalization.
// EXPORTS: resolveTheme, getTerminalTheme, resolveTerminalDefaults, DEFAULT_TERMINAL_DEFAULTS.
// DOCS: agent_chat/plan_daemon_settings_store_2026-04-08.md

import type { ITheme } from '@xterm/xterm'
import type { DaemonTerminalSettings } from '@/lib/daemonApi'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export interface TerminalDefaults {
  theme: ResolvedTheme
  cols: number
  rows: number
  scrollback: number
  fontFamily: string
  fontSize: number
  lineHeight: number
  cursorBlink: boolean
}

export const THEME_STORAGE_KEY = 'silc-manager-theme'
export const DEFAULT_TERMINAL_DEFAULTS: TerminalDefaults = {
  theme: 'dark',
  cols: 120,
  rows: 30,
  scrollback: 5000,
  fontFamily: 'Menlo, Monaco, "Courier New", monospace',
  fontSize: 15,
  lineHeight: 1.05,
  cursorBlink: true,
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== 'system') {
    return preference
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function getTerminalTheme(theme: ResolvedTheme): ITheme {
  if (theme === 'light') {
    return {
      background: '#fffbf5',
      foreground: '#1f2937',
      cursor: '#d97706',
      selectionBackground: '#d9770633',
      black: '#1f2937',
      red: '#c2410c',
      green: '#3f6212',
      yellow: '#b45309',
      blue: '#1d4ed8',
      magenta: '#9d174d',
      cyan: '#0f766e',
      white: '#f8fafc',
      brightBlack: '#6b7280',
      brightRed: '#ea580c',
      brightGreen: '#65a30d',
      brightYellow: '#d97706',
      brightBlue: '#2563eb',
      brightMagenta: '#be185d',
      brightCyan: '#0d9488',
      brightWhite: '#ffffff',
    }
  }

  return {
    background: '#1f232b',
    foreground: '#f3f4f6',
    cursor: '#f97316',
    selectionBackground: '#f9731644',
    black: '#111827',
    red: '#f87171',
    green: '#4ade80',
    yellow: '#fbbf24',
    blue: '#60a5fa',
    magenta: '#fb7185',
    cyan: '#22d3ee',
    white: '#f9fafb',
    brightBlack: '#6b7280',
    brightRed: '#fca5a5',
    brightGreen: '#86efac',
    brightYellow: '#fcd34d',
    brightBlue: '#93c5fd',
    brightMagenta: '#fda4af',
    brightCyan: '#67e8f9',
    brightWhite: '#ffffff',
  }
}

export function resolveTerminalDefaults(
  settings?: Partial<DaemonTerminalSettings>,
): TerminalDefaults {
  const theme =
    settings?.theme === 'light'
      ? 'light'
      : settings?.theme === 'dark'
        ? 'dark'
        : DEFAULT_TERMINAL_DEFAULTS.theme

  return {
    theme,
    cols: settings?.cols ?? DEFAULT_TERMINAL_DEFAULTS.cols,
    rows: settings?.rows ?? DEFAULT_TERMINAL_DEFAULTS.rows,
    scrollback: settings?.scrollback ?? DEFAULT_TERMINAL_DEFAULTS.scrollback,
    fontFamily: settings?.fontFamily ?? DEFAULT_TERMINAL_DEFAULTS.fontFamily,
    fontSize: settings?.fontSize ?? DEFAULT_TERMINAL_DEFAULTS.fontSize,
    lineHeight: settings?.lineHeight ?? DEFAULT_TERMINAL_DEFAULTS.lineHeight,
    cursorBlink: settings?.cursorBlink ?? DEFAULT_TERMINAL_DEFAULTS.cursorBlink,
  }
}
