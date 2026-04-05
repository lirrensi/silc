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
  terminal: { onData: vi.fn().mockReturnValue({ dispose: vi.fn() }), clear: vi.fn() },
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
})
