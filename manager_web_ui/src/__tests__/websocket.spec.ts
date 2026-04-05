// FILE: manager_web_ui/src/__tests__/websocket.spec.ts
// PURPOSE: Verify websocket frames update title and hidden cwd state in the store.
// OWNS: Websocket client coverage for terminal metadata frames.
// DOCS: agent_chat/plan_hidden_cwd_prompt_2026-04-05.md

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { connectWebSocket } from '../lib/websocket'
import { encodeWsFrame } from '../lib/websocketFrame'

const session = {
  ws: null as WebSocket | null,
  title: '',
  cwd: null as string | null,
  titleUpdatedAt: null as string | null,
  isRestoring: false,
  onDataDisposable: null as null | { dispose: ReturnType<typeof vi.fn> },
  terminal: {
    onData: vi.fn().mockReturnValue({ dispose: vi.fn() }),
    clear: vi.fn(),
    reset: vi.fn(),
    write: vi.fn(),
  },
}

const manager = {
  getSession: vi.fn(() => session),
  setWs: vi.fn((_, ws) => {
    session.ws = ws
  }),
  setStatus: vi.fn(),
  setDisconnectReason: vi.fn(),
  scheduleFit: vi.fn(),
  flushWrites: vi.fn().mockResolvedValue(undefined),
  safeWrite: vi.fn(),
  refreshTerminalSurface: vi.fn(),
  resolveHistoryRefresh: vi.fn(),
  cancelHistoryRefresh: vi.fn(() => {
    session.isRestoring = false
  }),
  updateSessionTitle: vi.fn((_, title, updatedAt) => {
    session.title = title
    session.titleUpdatedAt = updatedAt
  }),
  updateSessionCwd: vi.fn((_, cwd) => {
    session.cwd = cwd
  }),
}

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  onopen: null | ((event: Event) => void) = null
  onmessage: null | ((event: MessageEvent) => void) = null
  onclose: null | ((event: CloseEvent) => void) = null
  onerror: null | ((event: Event) => void) = null
  send = vi.fn()
  close = vi.fn()

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }
}

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => manager,
}))

vi.mock('@/lib/daemonApi', () => ({
  getSessionHttpUrl: () => 'http://127.0.0.1:20000',
}))

describe('connectWebSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    session.ws = null
    session.title = ''
    session.cwd = null
    session.titleUpdatedAt = null
    session.isRestoring = false
    session.onDataDisposable = null
    session.terminal.clear.mockClear()
    session.terminal.reset.mockClear()
    session.terminal.write.mockClear()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  it('updates the session title immediately from websocket events', async () => {
    const ws = connectWebSocket(20000)
    expect(ws).toBeTruthy()

    ws?.onopen?.(new Event('open'))
    expect(manager.setStatus).toHaveBeenCalledWith(20000, 'active')

    ws?.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame(
          {
            type: 'title',
            title: 'PowerShell - npm run dev',
            title_updated_at: '2026-04-05T00:00:00Z',
          },
        ).buffer,
      }),
    )

    expect(manager.updateSessionTitle).toHaveBeenCalledWith(
      20000,
      'PowerShell - npm run dev',
      '2026-04-05T00:00:00Z',
    )
    expect(session.title).toBe('PowerShell - npm run dev')
  })

  it('updates the session cwd immediately from websocket events', async () => {
    const ws = connectWebSocket(20000)
    expect(ws).toBeTruthy()

    ws?.onopen?.(new Event('open'))

    ws?.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({ type: 'cwd', cwd: 'C:/Temp/Project' }).buffer,
      }),
    )

    expect(manager.updateSessionCwd).toHaveBeenCalledWith(20000, 'C:/Temp/Project')
    expect(session.cwd).toBe('C:/Temp/Project')
  })

  it('resets the terminal before replaying history', async () => {
    const ws = connectWebSocket(20000)
    expect(ws).toBeTruthy()

    ws?.onopen?.(new Event('open'))

    await ws?.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({ type: 'history' }, new TextEncoder().encode('\u001b[31mRED\u001b[0m')).buffer,
      }),
    )

    expect(session.terminal.reset).toHaveBeenCalled()
    expect(session.terminal.clear).not.toHaveBeenCalled()
    expect(manager.safeWrite).toHaveBeenCalledWith(20000, expect.any(Uint8Array))
  })

  it('rebinds input on an already-open websocket for a fresh terminal instance', () => {
    const dispose = vi.fn()
    session.onDataDisposable = { dispose }

    const ws = connectWebSocket(20000)
    if (ws) {
      Object.defineProperty(ws, 'readyState', { value: MockWebSocket.OPEN })
      session.ws = ws
    }

    session.terminal.onData.mockClear()

    const reopened = connectWebSocket(20000)

    expect(reopened).toBe(ws)
    expect(dispose).toHaveBeenCalled()
    expect(session.terminal.onData).toHaveBeenCalled()
  })

  it('swallows terminal DA probes before they reach the backend', () => {
    const ws = connectWebSocket(20000) as MockWebSocket | null
    expect(ws).toBeTruthy()

    ws?.onopen?.(new Event('open'))

    const onData = session.terminal.onData.mock.calls[0]?.[0] as ((data: string) => void) | undefined
    expect(onData).toBeTruthy()

    const socket = ws as MockWebSocket
    const sendsBeforeProbe = socket.send.mock.calls.length
    onData?.('\x1b[?1;2c')
    expect(socket.send.mock.calls.length).toBe(sendsBeforeProbe)

    onData?.('a')
    expect(ws?.send).toHaveBeenCalled()
  })

  it('cancels a stuck restore when the websocket closes early', () => {
    const ws = connectWebSocket(20000)
    expect(ws).toBeTruthy()

    session.isRestoring = true
    ws?.onclose?.({ reason: 'closed' } as CloseEvent)

    expect(manager.cancelHistoryRefresh).toHaveBeenCalledWith(20000)
    expect(session.isRestoring).toBe(false)
  })

  it('cancels a stuck restore when the websocket errors during replay', () => {
    const ws = connectWebSocket(20000)
    expect(ws).toBeTruthy()

    session.isRestoring = true
    ws?.onerror?.(new Event('error'))

    expect(manager.cancelHistoryRefresh).toHaveBeenCalledWith(20000)
    expect(session.isRestoring).toBe(false)
  })
})
