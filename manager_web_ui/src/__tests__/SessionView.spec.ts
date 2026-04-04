// FILE: manager_web_ui/src/__tests__/SessionView.spec.ts
// PURPOSE: Guard the interactive session page from inheriting the Home-only selector.
// OWNS: Session route smoke coverage for selector isolation.
// DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionView from '../views/SessionView.vue'

vi.mock('@/lib/daemonApi', () => ({
  closeSession: vi.fn(),
  killSession: vi.fn(),
  listSessions: vi.fn().mockResolvedValue([]),
  restartSession: vi.fn(),
  sendInterrupt: vi.fn(),
  sendSigkill: vi.fn(),
  sendSigterm: vi.fn(),
}))

vi.mock('@/lib/websocket', () => ({
  connectWebSocket: vi.fn(),
}))

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    setFocused: vi.fn(),
    getSession: () => ({
      status: 'idle',
      ws: null,
      title: 'demo',
      name: 'demo',
      shell: 'bash',
      cwd: null,
      disconnectReason: null,
      terminal: { reset: vi.fn(), scrollToBottom: vi.fn() },
    }),
    flushWrites: vi.fn().mockResolvedValue(undefined),
    waitForHistoryRefresh: vi.fn().mockResolvedValue(undefined),
    resolveHistoryRefresh: vi.fn(),
    refreshTerminalSurface: vi.fn(),
    forceRedraw: vi.fn(),
    removeSession: vi.fn(),
    setStatus: vi.fn(),
    reconcileSessions: vi.fn(),
  }),
}))

describe('SessionView', () => {
  beforeEach(() => {
    localStorage.clear()
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

  it('does not render the Home grid selector', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/:port(\\d+)', component: SessionView, props: true }],
    })

    await router.push('/1234')
    await router.isReady()

    const wrapper = mount(SessionView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          TerminalViewport: true,
          Teleport: true,
        },
      },
    })

    expect(wrapper.text()).not.toContain('2x2')
    expect(wrapper.text()).not.toContain('3x3')
    expect(wrapper.text()).not.toContain('4x4')
  })
})
