import type { ITheme } from '@xterm/xterm'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'silc-manager-theme'

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
