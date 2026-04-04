// FILE: manager_web_ui/src/__tests__/SessionView.spec.ts
// PURPOSE: Guard the interactive session page from inheriting the Home-only selector.
// OWNS: Session route smoke coverage for selector isolation.
// DOCS: agent_chat/plan_home_grid_frozen_previews_2026-04-04.md

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { SessionStatus } from '@/types/session'
import SessionView from '../views/SessionView.vue'

const mockSendInputFrame = vi.hoisted(() => vi.fn())

const session = {
  status: 'idle' as SessionStatus,
  ws: null as WebSocket | null,
  title: 'demo',
  name: 'demo',
  shell: 'bash',
  cwd: null as string | null,
  disconnectReason: null as string | null,
  terminal: { reset: vi.fn(), scrollToBottom: vi.fn() },
}

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
  requestHistoryFrame: vi.fn(),
  sendInputFrame: mockSendInputFrame,
}))

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    setFocused: vi.fn(),
    getSession: () => session,
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
    session.ws = null
    mockSendInputFrame.mockClear()
    session.terminal.reset.mockClear()
    session.terminal.scrollToBottom.mockClear()
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
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        readText: vi.fn(),
      },
    })
  })

  it('does not render the Home grid selector', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/:port(\\d+)', component: SessionView, props: true }],
    })

    await router.push('/1234')
    await router.isReady()

    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

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

  it('keeps bottom and arrow actions silent', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/:port(\\d+)', component: SessionView, props: true }],
    })

    await router.push('/1234')
    await router.isReady()

    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const wrapper = mount(SessionView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          TerminalViewport: true,
          Teleport: true,
        },
      },
    })

    const buttons = wrapper.findAll('button')
    const bottomButton = buttons.find((button) => button.text() === 'Bottom')
    const upButton = buttons.find((button) => button.text() === '↑')

    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    await bottomButton?.trigger('click')
    await upButton?.trigger('click')

    expect(wrapper.text()).not.toContain('Processing')
    expect(session.terminal.scrollToBottom).toHaveBeenCalled()
    expect(mockSendInputFrame).toHaveBeenCalledWith(expect.anything(), '\x1b[A')
  })

  it('pastes clipboard text directly without a modal', async () => {
    const readText = vi.fn().mockResolvedValue('echo hello')
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { readText },
    })
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket
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

    const pasteButton = wrapper.findAll('button').find((button) => button.text() === 'Paste')
    await pasteButton?.trigger('click')

    expect(readText).toHaveBeenCalled()
    expect(mockSendInputFrame).toHaveBeenCalledWith(expect.anything(), 'echo hello')
    expect(wrapper.text()).not.toContain('Paste text into shell')
    expect(wrapper.text()).not.toContain('Processing')
  })
})
