// FILE: manager_web_ui/src/__tests__/TerminalViewport.spec.ts
// PURPOSE: Verify session terminal reattach behavior triggers a fresh history replay.
// OWNS: Terminal viewport attach and reconnect behavior coverage.

import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TerminalViewport from '../components/TerminalViewport.vue'

const mocks = vi.hoisted(() => {
  const requestHistoryFrame = vi.fn()
  const connectWebSocket = vi.fn()
  const session = {
    terminal: {
      element: {} as HTMLElement,
    },
    ws: { readyState: 1 } as WebSocket,
  }
  const manager = {
    getSession: vi.fn(() => session),
    attach: vi.fn(),
    detach: vi.fn(),
    setFocused: vi.fn(),
    scheduleFit: vi.fn(),
    reconcileSessions: vi.fn(),
  }

  return { requestHistoryFrame, connectWebSocket, session, manager }
})

vi.mock('@/lib/daemonApi', () => ({
  listSessions: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/lib/websocket', () => ({
  connectWebSocket: mocks.connectWebSocket,
  requestHistoryFrame: mocks.requestHistoryFrame,
}))

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => mocks.manager,
}))

describe('TerminalViewport', () => {
  beforeEach(() => {
    mocks.requestHistoryFrame.mockClear()
    mocks.connectWebSocket.mockClear()
    mocks.manager.getSession.mockClear()
    mocks.manager.attach.mockClear()
    mocks.manager.detach.mockClear()
    mocks.manager.setFocused.mockClear()
    mocks.manager.scheduleFit.mockClear()
    mocks.manager.reconcileSessions.mockClear()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn()
        disconnect = vi.fn()
      } as unknown as typeof ResizeObserver,
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests history when reattaching an existing terminal element', async () => {
    const wrapper = mount(TerminalViewport, {
      global: {
        plugins: [createPinia()],
      },
      props: {
        port: 20000,
        interactive: true,
      },
    })

    await wrapper.vm.$nextTick()

    expect(mocks.manager.attach).toHaveBeenCalled()
    expect(mocks.connectWebSocket).not.toHaveBeenCalled()
    expect(mocks.requestHistoryFrame).toHaveBeenCalledWith(mocks.session.ws)
  })
})
