// FILE: manager_web_ui/src/lib/websocket.ts
// PURPOSE: Connect session terminals to the daemon websocket while preserving ordered history and repaint recovery.
// OWNS: Websocket lifecycle for terminal sessions and history/output/title message handling.
// EXPORTS: connectWebSocket - open or replace a session websocket; disconnectWebSocket - close a session websocket intentionally.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { getSessionHttpUrl } from '@/lib/daemonApi'
import { decodeWsFrame, requestHistoryFrame, sendInputFrame } from '@/lib/websocketFrame'
import { useTerminalManager } from '@/stores/terminalManager'

export { decodeWsFrame, encodeWsFrame, requestHistoryFrame, sendInputFrame, sendWsFrame } from '@/lib/websocketFrame'

export function connectWebSocket(port: number, options?: { force?: boolean }): WebSocket | null {
  console.log(`[WebSocket] connectWebSocket(${port})`)
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) {
    console.error(`[WebSocket] No session found for port ${port}`)
    return null
  }

  const existingWs = session.ws
  if (existingWs && !options?.force && (existingWs.readyState === WebSocket.OPEN || existingWs.readyState === WebSocket.CONNECTING)) {
    return existingWs
  }

  if (existingWs) {
    console.log(`[WebSocket] Closing existing connection for port ${port}`)
    manager.setWs(port, null)
    existingWs.close()
  }

  const wsBase = getSessionHttpUrl(port).replace(/^http/, 'ws')
  const wsUrl = `${wsBase}/ws`
  console.log(`[WebSocket] Connecting to ${wsUrl}`)
  const ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'
  manager.setWs(port, ws)
  manager.setStatus(port, 'connecting')

  ws.onopen = () => {
    if (manager.getSession(port)?.ws !== ws) {
      ws.close()
      return
    }
    console.log(`[WebSocket] Connected to port ${port}`)
    manager.setDisconnectReason(port, null)
    manager.setStatus(port, 'active')
    requestHistoryFrame(ws)
    manager.updateSessionTitle(port, session.title || '', session.titleUpdatedAt)
    manager.scheduleFit(port, { immediate: true, reason: 'ws-open' })
  }

  ws.onmessage = async (event) => {
    try {
      if (!(event.data instanceof ArrayBuffer)) {
        throw new Error('Expected binary websocket frame')
      }

      const { header, payload } = decodeWsFrame(event.data)

      if (header.type === 'history') {
        await manager.flushWrites(port)
        session.terminal.clear()
        if (payload.byteLength > 0) {
          manager.safeWrite(port, payload)
        }
        await manager.flushWrites(port)
        manager.refreshTerminalSurface(port)
        manager.resolveHistoryRefresh(port)
      } else if (header.type === 'output') {
        if (payload.byteLength > 0) {
          manager.safeWrite(port, payload)
        }
      } else if (header.type === 'title' && typeof header.title === 'string') {
        manager.updateSessionTitle(
          port,
          header.title,
          typeof header.title_updated_at === 'string' ? header.title_updated_at : null,
        )
      } else {
        throw new Error(`Unsupported websocket frame type: ${String(header.type)}`)
      }
    } catch (err) {
      console.error(`[WebSocket] Frame handling failed for port ${port}:`, err)
      if (ws.readyState === WebSocket.OPEN) {
        ws.close(1002, 'Invalid websocket frame')
      }
    }
  }

  ws.onclose = (event) => {
    const currentSession = manager.getSession(port)
    if (!currentSession || currentSession.ws !== ws) {
      return
    }
    console.log(`[WebSocket] Connection closed for port ${port}`)
    manager.setWs(port, null)

    if (currentSession.status === 'restarting') {
      return
    }

    manager.setDisconnectReason(port, event.reason || null)
    manager.setStatus(port, currentSession.status === 'connecting' ? 'dead' : 'idle')
  }

  ws.onerror = (err) => {
    if (manager.getSession(port)?.ws !== ws) {
      return
    }
    console.error(`[WebSocket] Error for port ${port}:`, err)
    manager.setDisconnectReason(port, 'WebSocket transport error')
    manager.setStatus(port, 'dead')
  }

  session.onDataDisposable?.dispose()
  session.onDataDisposable = session.terminal.onData((data: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      sendInputFrame(ws, data)
    }
  })

  return ws
}

export function disconnectWebSocket(port: number): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (session?.ws) {
    const ws = session.ws
    manager.setWs(port, null)
    manager.setDisconnectReason(port, null)
    manager.setStatus(port, 'idle')
    ws.close()
  }
}
