// FILE: manager_web_ui/src/__tests__/TerminalViewport.spec.ts
// PURPOSE: Verify restored terminals stay hidden during replay and request history on reconnect.
// OWNS: Terminal viewport attach, reconnect, and restoration visibility coverage.

import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import TerminalViewport from '../components/TerminalViewport.vue'

let session: {
  terminal: { element: HTMLElement }
  ws: WebSocket | null
  isRestoring: boolean
}

const mocks = vi.hoisted(() => {
  const requestHistoryFrame = vi.fn()
  const connectWebSocket = vi.fn()
  const manager = {
    getSession: vi.fn(() => session),
    attach: vi.fn(),
    detach: vi.fn(),
    setFocused: vi.fn(),
    scheduleFit: vi.fn(),
    reconcileSessions: vi.fn(),
  }

  return { requestHistoryFrame, connectWebSocket, manager }
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
    session = reactive({
      terminal: {
        element: {} as HTMLElement,
      },
      ws: { readyState: 1 } as WebSocket,
      isRestoring: true,
    })
    mocks.connectWebSocket.mockReturnValue(session.ws as WebSocket)
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

  it('keeps a restored terminal hidden until replay completes', async () => {
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

    expect(mocks.manager.attach).toHaveBeenCalledWith(
      20000,
      expect.any(HTMLElement),
      { propagate: true },
    )
    expect(mocks.connectWebSocket).toHaveBeenCalledWith(20000)
    expect(mocks.requestHistoryFrame).toHaveBeenCalledWith(session.ws)
    expect(wrapper.find('.terminal-host').classes()).toContain('terminal-host--restoring')

    session.isRestoring = false
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.terminal-host').classes()).not.toContain('terminal-host--restoring')
  })
})
