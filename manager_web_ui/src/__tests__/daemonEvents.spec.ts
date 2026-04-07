// FILE: manager_web_ui/src/__tests__/daemonEvents.spec.ts
// PURPOSE: Verify daemon manager websocket events reconcile and mutate session state from framed binary messages.
// OWNS: Daemon events client coverage for snapshot bootstrap, per-session updates, removals, and reorder refresh behavior.
// DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md, agent_chat/plan_manager_qol_2026-04-05.md

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { startDaemonEvents, stopDaemonEvents } from '../lib/daemonEvents'
import { encodeWsFrame } from '../lib/websocketFrame'

const reconcileSessions = vi.fn()
const upsertDaemonSession = vi.fn()
const removeSession = vi.fn()

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    reconcileSessions,
    upsertDaemonSession,
    removeSession,
  }),
}))

vi.mock('@/lib/daemonApi', () => ({
  getDaemonUrl: () => 'http://127.0.0.1:19999',
  getSettings: vi.fn().mockResolvedValue({ ui: { themePreference: 'system' }, terminal: {} }),
  updateSettings: vi.fn(),
}))

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  binaryType = 'blob'
  onopen: null | ((event: Event) => void) = null
  onmessage: null | ((event: MessageEvent) => void) = null
  onclose: null | ((event: CloseEvent) => void) = null
  onerror: null | ((event: Event) => void) = null
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }
}

describe('daemonEvents', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  it('reconciles the store from a session snapshot frame', () => {
    const ws = startDaemonEvents()

    ws.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({
          type: 'session/snapshot',
          sessions: [{ port: 20000, name: 'alpha', title: '', session_id: 'sess-1', shell: 'bash', cwd: null, title_updated_at: null, idle_seconds: 0, alive: true, runtime_state: 'running', dormant: false }],
        }).buffer,
      }),
    )

    expect(reconcileSessions).toHaveBeenCalledWith([
      expect.objectContaining({ port: 20000, runtime_state: 'running' }),
    ])
  })

  it('reconciles reordered sessions from a reorder event', () => {
    const ws = startDaemonEvents()

    ws.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({
          type: 'session/reordered',
          sessions: [
            { port: 20002, name: 'beta', title: '', session_id: 'sess-2', shell: 'bash', cwd: null, title_updated_at: null, idle_seconds: 0, alive: true, runtime_state: 'running', dormant: false },
            { port: 20001, name: 'alpha', title: '', session_id: 'sess-1', shell: 'bash', cwd: null, title_updated_at: null, idle_seconds: 0, alive: true, runtime_state: 'running', dormant: false },
          ],
        }).buffer,
      }),
    )

    expect(reconcileSessions).toHaveBeenCalledWith([
      expect.objectContaining({ port: 20002 }),
      expect.objectContaining({ port: 20001 }),
    ])
  })

  it('upserts a single session update event', () => {
    const ws = startDaemonEvents()

    ws.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({
          type: 'session/updated',
          session: { port: 20001, name: 'beta', title: 'shell', session_id: 'sess-2', shell: 'bash', cwd: '/tmp', title_updated_at: null, idle_seconds: 0, alive: true, runtime_state: 'running', dormant: false },
        }).buffer,
      }),
    )

    expect(upsertDaemonSession).toHaveBeenCalledWith(
      expect.objectContaining({ port: 20001, cwd: '/tmp' }),
    )
  })

  it('removes a session on session/removed', () => {
    const ws = startDaemonEvents()

    ws.onmessage?.(
      new MessageEvent('message', {
        data: encodeWsFrame({
          type: 'session/removed',
          session: { port: 20002, name: 'gamma', title: '', session_id: 'sess-3', shell: 'bash', cwd: null, title_updated_at: null, idle_seconds: 0, alive: false, runtime_state: 'stopped', dormant: false },
        }).buffer,
      }),
    )

    expect(removeSession).toHaveBeenCalledWith(20002)
  })

  it('does not open duplicate sockets while one is active', () => {
    const first = startDaemonEvents() as unknown as MockWebSocket
    first.readyState = MockWebSocket.OPEN

    const second = startDaemonEvents()

    expect(second).toBe(first)
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('reconnects after an unexpected close', () => {
    const first = startDaemonEvents()

    first.onclose?.(new CloseEvent('close'))
    vi.advanceTimersByTime(1000)

    expect(MockWebSocket.instances).toHaveLength(2)
  })

  afterEach(() => {
    stopDaemonEvents()
    vi.useRealTimers()
  })
})
