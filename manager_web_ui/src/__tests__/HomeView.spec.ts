// FILE: manager_web_ui/src/__tests__/HomeView.spec.ts
// PURPOSE: Verify the Home-only density selector and frozen preview grid behavior.
// OWNS: Home layout selector coverage and Home grid slicing assertions.
// DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md

import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import HomeView from '../views/HomeView.vue'

const reconcileSessions = vi.fn()

vi.mock('@/lib/daemonApi', () => ({
  listSessions: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    sessionList: [
      { port: 1101 },
      { port: 1102 },
      { port: 1103 },
      { port: 1104 },
      { port: 1105 },
    ],
    reconcileSessions,
  }),
}))

describe('HomeView', () => {
  beforeEach(() => {
    localStorage.clear()
    reconcileSessions.mockClear()
  })

  it('shows the Home-only grid selector and slices the visible cards', async () => {
    localStorage.setItem('silc.homeGridDensity', '2x2')

    const wrapper = mount(HomeView, {
      global: {
        plugins: [createPinia()],
        stubs: {
          SessionCard: {
            template: '<div class="session-card-stub"><slot /></div>',
          },
          FrozenTerminalPreview: true,
        },
      },
    })

    await Promise.resolve()
    await Promise.resolve()

    expect(wrapper.text()).toContain('Home layout')
    expect(wrapper.find('[aria-pressed="true"]').text()).toBe('2x2')
    expect(wrapper.findAll('.session-card-stub')).toHaveLength(4)
    expect(reconcileSessions).toHaveBeenCalled()
  })
})
