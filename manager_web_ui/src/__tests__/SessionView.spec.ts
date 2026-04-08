// FILE: manager_web_ui/src/__tests__/SessionView.spec.ts
// PURPOSE: Verify the session route keeps its command controls and terminal actions wired to the daemon helpers.
// OWNS: Session route command-label coverage and single-session command dispatch assertions.
// DOCS: agent_chat/plan_manager_interface_commands_2026-04-08.md

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { SessionStatus } from '@/types/session'
import SessionView from '../views/SessionView.vue'

const mockSendInputFrame = vi.hoisted(() => vi.fn())
const mockPasteClipboardText = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockListSessions = vi.hoisted(() => vi.fn())
const mockRestartSession = vi.hoisted(() => vi.fn().mockResolvedValue({ port: 1234 }))
const mockRemoveSession = vi.hoisted(() => vi.fn())
const mockUnloadSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockClearSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockResetSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockCloseSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockKillSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockSendInterrupt = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockSendSigterm = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockSendSigkill = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))

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
  clearSession: mockClearSession,
  closeSession: mockCloseSession,
  killSession: mockKillSession,
  listSessions: mockListSessions,
  getSettings: vi.fn().mockResolvedValue({ ui: { themePreference: 'system' }, terminal: {} }),
  resetSession: mockResetSession,
  restartSession: mockRestartSession,
  sendInterrupt: mockSendInterrupt,
  sendSigkill: mockSendSigkill,
  sendSigterm: mockSendSigterm,
  unloadSession: mockUnloadSession,
  updateSettings: vi.fn(),
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
    pasteClipboardText: mockPasteClipboardText,
    flushWrites: vi.fn().mockResolvedValue(undefined),
    waitForHistoryRefresh: vi.fn().mockResolvedValue(undefined),
    resolveHistoryRefresh: vi.fn(),
    refreshTerminalSurface: vi.fn(),
    forceRedraw: vi.fn(),
    removeSession: mockRemoveSession,
    setStatus: vi.fn(),
    reconcileSessions: vi.fn(),
  }),
}))

async function mountView() {
  const router = createRouter({
    history: createWebHashHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/:port(\\d+)', component: SessionView, props: true },
    ],
  })

  await router.push('/1234')
  await router.isReady()

  return mount(SessionView, {
    global: {
      plugins: [createPinia(), router],
      stubs: {
        TerminalViewport: true,
        Teleport: true,
      },
    },
  })
}

describe('SessionView', () => {
  beforeEach(() => {
    localStorage.clear()
    session.status = 'idle'
    session.ws = null
    mockListSessions.mockResolvedValue([
      {
        port: 1234,
        name: 'demo',
        title: 'demo',
        session_id: 'sess-1',
        shell: 'bash',
        cwd: null,
        title_updated_at: null,
        idle_seconds: 0,
        alive: true,
        runtime_state: 'running',
        dormant: false,
      },
    ])
    mockSendInputFrame.mockClear()
    mockPasteClipboardText.mockClear()
    mockRestartSession.mockClear()
    mockUnloadSession.mockClear()
    mockClearSession.mockClear()
    mockResetSession.mockClear()
    mockCloseSession.mockClear()
    mockKillSession.mockClear()
    mockSendInterrupt.mockClear()
    mockSendSigterm.mockClear()
    mockSendSigkill.mockClear()
    session.terminal.reset.mockClear()
    session.terminal.scrollToBottom.mockClear()
    mockRemoveSession.mockClear()
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
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const wrapper = await mountView()

    expect(wrapper.text()).not.toContain('2x2')
    expect(wrapper.text()).not.toContain('3x3')
    expect(wrapper.text()).not.toContain('4x4')
  })

  it('keeps bottom and arrow actions silent', async () => {
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const wrapper = await mountView()
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
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const wrapper = await mountView()

    const pasteButton = wrapper.findAll('button').find((button) => button.text() === 'Paste')
    await pasteButton?.trigger('click')

    expect(mockPasteClipboardText).toHaveBeenCalledWith(1234)
    expect(wrapper.text()).not.toContain('Paste text into shell')
    expect(wrapper.text()).not.toContain('Processing')
  })

  it('redirects home when the selected session is no longer in the registry', async () => {
    mockListSessions.mockResolvedValueOnce([])

    await mountView()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(mockRemoveSession).toHaveBeenCalledWith(1234)
  })

  it('wakes a dormant session before showing controls', async () => {
    session.status = 'dormant'
    mockListSessions.mockResolvedValueOnce([
      {
        port: 1234,
        name: 'demo',
        title: 'demo',
        session_id: 'sess-1',
        shell: 'bash',
        cwd: null,
        title_updated_at: null,
        idle_seconds: 0,
        alive: false,
        runtime_state: 'dormant',
        dormant: true,
      },
    ])
    mockListSessions.mockResolvedValue([
      {
        port: 1234,
        name: 'demo',
        title: 'demo',
        session_id: 'sess-1',
        shell: 'bash',
        cwd: null,
        title_updated_at: null,
        idle_seconds: 0,
        alive: true,
        runtime_state: 'running',
        dormant: false,
      },
    ])

    const wrapper = await mountView()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(mockRestartSession).toHaveBeenCalledWith(1234)
    expect(wrapper.text()).not.toContain('Sleeping session')
  })

  it('renders the requested command labels', async () => {
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const wrapper = await mountView()
    const text = wrapper.text()

    expect(text).toContain('Unload')
    expect(text).toContain('Restart')
    expect(text).toContain('Close Session')
    expect(text).toContain('Close Forcefully')
    expect(text).toContain('Clear')
    expect(text).toContain('Reset')
    expect(text).toContain('SIGINT')
    expect(text).toContain('SIGTERM')
    expect(text).toContain('SIGKILL')
  })

  it('invokes the new single-session command helpers', async () => {
    session.status = 'active'
    session.ws = { readyState: WebSocket.OPEN } as WebSocket

    const triggerAction = async (label: string): Promise<void> => {
      const wrapper = await mountView()
      await wrapper.findAll('button').find((button) => button.text() === label)?.trigger('click')
      await flushPromises()
      await new Promise((resolve) => window.setTimeout(resolve, 260))
      wrapper.unmount()
    }

    await triggerAction('Unload')
    await triggerAction('Clear')
    await triggerAction('Reset')
    await triggerAction('Close Session')
    await triggerAction('Close Forcefully')
    await triggerAction('SIGINT')
    await triggerAction('SIGTERM')
    await triggerAction('SIGKILL')

    expect(mockUnloadSession).toHaveBeenCalledWith(1234)
    expect(mockClearSession).toHaveBeenCalledWith(1234)
    expect(mockResetSession).toHaveBeenCalledWith(1234)
    expect(mockCloseSession).toHaveBeenCalledWith(1234)
    expect(mockKillSession).toHaveBeenCalledWith(1234)
    expect(mockSendInterrupt).toHaveBeenCalledWith(1234)
    expect(mockSendSigterm).toHaveBeenCalledWith(1234)
    expect(mockSendSigkill).toHaveBeenCalledWith(1234)
  })
})
