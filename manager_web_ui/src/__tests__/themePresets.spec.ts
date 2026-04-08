// FILE: manager_web_ui/src/__tests__/themePresets.spec.ts
// PURPOSE: Verify the theme preset catalog shape and light/dark coverage.
// OWNS: Theme preset catalog regression coverage.
// DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md

import { describe, expect, it } from 'vitest'
import { THEME_PRESET_NAMES, THEME_PRESET_OPTIONS } from '@/lib/themePresets'

describe('themePresets', () => {
  it('includes a broader preset catalog with multiple light themes', () => {
    expect(THEME_PRESET_OPTIONS).toHaveLength(THEME_PRESET_NAMES.length)
    expect(THEME_PRESET_OPTIONS.length).toBeGreaterThanOrEqual(10)

    const lightPresets = THEME_PRESET_OPTIONS.filter(option => option.mode === 'light').map(option => option.value)

    expect(lightPresets).toEqual(expect.arrayContaining(['github', 'vercel', 'solarized', 'oc-2']))
    expect(lightPresets.length).toBeGreaterThanOrEqual(4)
  })
})
