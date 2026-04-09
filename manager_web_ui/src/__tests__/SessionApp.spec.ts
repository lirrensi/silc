// FILE: manager_web_ui/src/__tests__/SessionApp.spec.ts
// PURPOSE: Verify the standalone session shell stays in-place and shows an end-state splash for destructive exits.
// OWNS: Standalone session destructive-action overlay coverage and Close Window behavior.
// DOCS: agent_chat/plan_session_end_splash_2026-04-09.md

import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { SessionStatus } from '@/types/session'
import SessionShell from '@/components/SessionShell.vue'

const mockSendInputFrame = vi.hoisted(() => vi.fn())
const mockListSessions = vi.hoisted(() => vi.fn())
const mockRestartSession = vi.hoisted(() => vi.fn().mockResolvedValue({ port: 1234 }))
const mockUnloadSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockCloseSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockKillSession = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockApplyMeasuredFit = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const mockWindowClose = vi.hoisted(() => vi.fn())

type MockSession = {
  status: SessionStatus
  ws: WebSocket | null
  title: string
  name: string
  shell: string
  cwd: string | null
  disconnectReason: string | null
  terminal: { reset: ReturnType<typeof vi.fn>; scrollToBottom: ReturnType<typeof vi.fn> } | null
}

let currentSession: MockSession | undefined

function makeSession(): MockSession {
  return {
    status: 'active',
    ws: { readyState: WebSocket.OPEN } as WebSocket,
    title: 'demo',
    name: 'demo',
    shell: 'bash',
    cwd: null,
    disconnectReason: null,
    terminal: { reset: vi.fn(), scrollToBottom: vi.fn() },
  }
}

vi.mock('@/lib/daemonApi', () => ({
  clearSession: vi.fn().mockResolvedValue(undefined),
  closeSession: mockCloseSession,
  killSession: mockKillSession,
  listSessions: mockListSessions,
  restartSession: mockRestartSession,
  sendInterrupt: vi.fn().mockResolvedValue(undefined),
  sendSigkill: vi.fn().mockResolvedValue(undefined),
  sendSigterm: vi.fn().mockResolvedValue(undefined),
  unloadSession: mockUnloadSession,
}))

vi.mock('@/lib/websocket', () => ({
  connectWebSocket: vi.fn(),
  requestHistoryFrame: vi.fn(),
  sendInputFrame: mockSendInputFrame,
}))

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    setFocused: vi.fn(),
    getSession: () => currentSession,
    pasteClipboardText: vi.fn().mockResolvedValue(undefined),
    flushWrites: vi.fn().mockResolvedValue(undefined),
    waitForHistoryRefresh: vi.fn().mockResolvedValue(undefined),
    resolveHistoryRefresh: vi.fn(),
    applyMeasuredFit: mockApplyMeasuredFit,
    refreshTerminalSurface: vi.fn(),
    forceRedraw: vi.fn(),
    removeSession: vi.fn((port: number) => {
      if (currentSession && port === 1234) {
        currentSession = undefined
      }
    }),
    setStatus: vi.fn((port: number, status: SessionStatus) => {
      if (currentSession && port === 1234) {
        currentSession.status = status
      }
    }),
    reconcileSessions: vi.fn(),
  }),
}))

function mountShell() {
  return mount(SessionShell, {
    props: {
      port: 1234,
      surface: 'standalone',
    },
    global: {
      plugins: [createPinia()],
      stubs: {
        TerminalViewport: true,
      },
    },
  })
}

describe('SessionApp standalone shell', () => {
  beforeEach(() => {
    localStorage.clear()
    currentSession = makeSession()
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
    mockRestartSession.mockClear()
    mockUnloadSession.mockClear()
    mockCloseSession.mockClear()
    mockKillSession.mockClear()
    mockApplyMeasuredFit.mockClear()
    mockWindowClose.mockClear()
    Object.defineProperty(window, 'close', {
      writable: true,
      value: mockWindowClose,
    })
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

  it.each([
    ['Unload', mockUnloadSession],
    ['Close Session', mockCloseSession],
    ['Close Forcefully', mockKillSession],
  ])('shows the standalone end-state splash after %s', async (label, apiMock) => {
    const wrapper = mountShell()

    await wrapper.findAll('button').find((button) => button.text() === label)?.trigger('click')
    await flushPromises()
    await new Promise((resolve) => window.setTimeout(resolve, 260))

    expect(apiMock).toHaveBeenCalledWith(1234)
    expect(wrapper.text()).toContain('Session ended')
    expect(wrapper.text()).toContain('You can now close this page or window.')
    expect(wrapper.text()).toContain('Close Window')

    await wrapper.findAll('button').find((button) => button.text() === 'Close Window')?.trigger('click')

    expect(mockWindowClose).toHaveBeenCalledTimes(1)
  })

  it('keeps restart on the non-destructive reconnect path', async () => {
    const wrapper = mountShell()

    await wrapper.findAll('button').find((button) => button.text() === 'Restart')?.trigger('click')
    await flushPromises()
    await new Promise((resolve) => window.setTimeout(resolve, 430))

    expect(mockRestartSession).toHaveBeenCalledWith(1234)
    expect(wrapper.text()).not.toContain('Session ended')
    expect(wrapper.text()).not.toContain('Close Window')
  })
})
