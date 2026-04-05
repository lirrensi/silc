// FILE: manager_web_ui/src/lib/daemonEvents.ts
// PURPOSE: Keep manager session state synchronized from the daemon-level websocket event stream.
// OWNS: Daemon websocket lifecycle, binary frame decoding, store reconciliation, and reconnect handling.
// EXPORTS: startDaemonEvents - open or reuse the daemon event stream; stopDaemonEvents - close the daemon event stream.
// DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md

import { getDaemonUrl } from '@/lib/daemonApi'
import { decodeWsFrame } from '@/lib/websocketFrame'
import { useTerminalManager } from '@/stores/terminalManager'
import type { DaemonSession } from '@/types/session'

let daemonEventsSocket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | number | null = null
let intentionallyClosed = false

function getDaemonEventsUrl(): string {
  return `${getDaemonUrl().replace(/^http/, 'ws')}/events`
}

function clearReconnectTimer(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function handleSessionUpsert(session: DaemonSession): void {
  useTerminalManager().upsertDaemonSession(session)
}

export function startDaemonEvents(): WebSocket {
  if (daemonEventsSocket && (daemonEventsSocket.readyState === WebSocket.OPEN || daemonEventsSocket.readyState === WebSocket.CONNECTING)) {
    return daemonEventsSocket
  }

  intentionallyClosed = false
  clearReconnectTimer()

  const ws = new WebSocket(getDaemonEventsUrl())
  ws.binaryType = 'arraybuffer'
  daemonEventsSocket = ws

  ws.onmessage = (event) => {
    if (!(event.data instanceof ArrayBuffer)) {
      throw new Error('Expected binary daemon event frame')
    }

    const { header } = decodeWsFrame(event.data)
    const type = header.type
    const manager = useTerminalManager()

    if ((type === 'session/snapshot' || type === 'session/reordered') && Array.isArray(header.sessions)) {
      manager.reconcileSessions(header.sessions as DaemonSession[])
      return
    }

    if (type === 'session/removed' && header.session && typeof header.session === 'object') {
      const session = header.session as DaemonSession
      manager.removeSession(session.port)
      return
    }

    if (
      [
        'session/created',
        'session/started',
        'session/restarted',
        'session/renamed',
        'session/title_changed',
        'session/cwd_changed',
        'session/updated',
      ].includes(String(type))
      && header.session
      && typeof header.session === 'object'
    ) {
      handleSessionUpsert(header.session as DaemonSession)
    }
  }

  ws.onclose = () => {
    if (daemonEventsSocket === ws) {
      daemonEventsSocket = null
    }
    if (intentionallyClosed) {
      return
    }
    clearReconnectTimer()
    reconnectTimer = window.setTimeout(() => {
      if (!daemonEventsSocket) {
        startDaemonEvents()
      }
    }, 1000)
  }

  ws.onerror = () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close()
    }
  }

  return ws
}

export function stopDaemonEvents(): void {
  intentionallyClosed = true
  clearReconnectTimer()
  const ws = daemonEventsSocket
  daemonEventsSocket = null
  ws?.close()
}
