// FILE: manager_web_ui/src/lib/themePresets.ts
// PURPOSE: Resolve, apply, and enumerate the shared manager theme presets.
// OWNS: Theme preset lookup, browser theme application, and xterm theme resolution.
// EXPORTS: THEME_PRESET_OPTIONS, THEME_PRESET_NAMES, DEFAULT_MANAGER_THEME_PRESET, DEFAULT_TERMINAL_THEME_PRESET, getThemePresetMode, getTerminalThemePreset, getManagerThemeVariables, applyManagerThemePreset, resolveThemePreset.
// DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md

import type { ITheme } from '@xterm/xterm'
import {
  THEME_PRESET_CATALOG,
  type ThemePresetMode,
  type ThemePresetSpec,
} from './themePresetCatalog'

export type ThemePresetName = (typeof THEME_PRESET_CATALOG)[number]['name']

export interface ThemePresetOption {
  value: ThemePresetName
  label: string
  description: string
  mode: ThemePresetMode
}

export const THEME_PRESET_NAMES = THEME_PRESET_CATALOG.map(preset => preset.name) as ThemePresetName[]
export const DEFAULT_MANAGER_THEME_PRESET: ThemePresetName = 'github'
export const DEFAULT_TERMINAL_THEME_PRESET: ThemePresetName = 'amoled'

const THEME_PRESETS = Object.fromEntries(
  THEME_PRESET_CATALOG.map(preset => [preset.name, preset]),
) as Record<ThemePresetName, ThemePresetSpec>

export const THEME_PRESET_OPTIONS: ThemePresetOption[] = THEME_PRESET_CATALOG.map((preset) => ({
  value: preset.name,
  label: preset.label,
  description: preset.description,
  mode: preset.mode,
}))

export function resolveThemePreset(value: unknown, fallback: ThemePresetName = DEFAULT_MANAGER_THEME_PRESET): ThemePresetName {
  if (typeof value === 'string' && THEME_PRESET_NAMES.includes(value as ThemePresetName)) {
    return value as ThemePresetName
  }

  if (value === 'light') {
    return 'github'
  }

  if (value === 'dark') {
    return 'amoled'
  }

  if (value === 'system') {
    const prefersDark = typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false
    return prefersDark ? 'amoled' : 'github'
  }

  return fallback
}

export function getThemePresetMode(value: ThemePresetName): ThemePresetMode {
  return THEME_PRESETS[value].mode
}

export function getTerminalThemePreset(value: ThemePresetName): ITheme {
  return THEME_PRESETS[value].terminal
}

export function getManagerThemeVariables(value: ThemePresetName): Record<string, string> {
  const vars = THEME_PRESETS[value].vars

  return {
    '--color-bg-primary': vars.bgPrimary,
    '--color-bg-secondary': vars.bgSecondary,
    '--color-bg-tertiary': vars.bgTertiary,
    '--color-bg-hover': vars.bgHover,
    '--color-bg-elevated': vars.bgElevated,
    '--color-border': vars.border,
    '--color-border-strong': vars.borderStrong,
    '--color-text-primary': vars.textPrimary,
    '--color-text-secondary': vars.textSecondary,
    '--color-text-muted': vars.textMuted,
    '--color-accent': vars.accent,
    '--color-accent-strong': vars.accentStrong,
    '--color-accent-muted': vars.accentMuted,
    '--color-success': vars.success,
    '--color-warning': vars.warning,
    '--color-error': vars.error,
    '--color-idle': vars.idle,
    '--color-backdrop': vars.backdrop,
    '--color-shadow': vars.shadow,
  }
}

export function applyManagerThemePreset(value: ThemePresetName): void {
  if (typeof document === 'undefined') {
    return
  }

  const root = document.documentElement
  const spec = THEME_PRESETS[value]

  root.dataset.theme = spec.mode
  root.dataset.managerTheme = value
  root.style.colorScheme = spec.mode

  for (const [property, color] of Object.entries(getManagerThemeVariables(value))) {
    root.style.setProperty(property, color)
  }
}

export function getDefaultThemePresetForMode(mode: ThemePresetMode): ThemePresetName {
  return mode === 'light' ? 'github' : 'amoled'
}
