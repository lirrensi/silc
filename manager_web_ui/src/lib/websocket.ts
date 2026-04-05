// FILE: manager_web_ui/src/lib/websocket.ts
// PURPOSE: Connect session terminals to the daemon websocket while preserving ordered history and repaint recovery.
// OWNS: Websocket lifecycle for terminal sessions and history/output/title message handling.
// EXPORTS: connectWebSocket - open or replace a session websocket; disconnectWebSocket - close a session websocket intentionally.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { getSessionHttpUrl } from '@/lib/daemonApi'
import { decodeWsFrame, requestHistoryFrame, sendInputFrame } from '@/lib/websocketFrame'
import { useTerminalManager } from '@/stores/terminalManager'

export { decodeWsFrame, encodeWsFrame, requestHistoryFrame, sendInputFrame, sendWsFrame } from '@/lib/websocketFrame'

const SUPPRESSED_TERMINAL_INPUTS = new Set(['\x1b[c', '\x1b[0c', '\x1b[?1;2c'])

function bindTerminalInput(port: number, ws: WebSocket): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) {
    return
  }

  if (session.terminalDisposed) {
    return
  }

  session.onDataDisposable?.dispose()
  session.onDataDisposable = session.terminal.onData((data: string) => {
    if (SUPPRESSED_TERMINAL_INPUTS.has(data)) {
      return
    }

    if (ws.readyState === WebSocket.OPEN) {
      sendInputFrame(ws, data)
    }
  })
}

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
    bindTerminalInput(port, existingWs)
    return existingWs
  }

  if (existingWs) {
    console.log(`[WebSocket] Closing existing connection for port ${port}`)
    manager.setWs(port, null)
    existingWs.close()
  }

  const wsBase = getSessionHttpUrl(port).replace(/^http/, 'ws')
  const wsUrl = `${wsBase}/ws?mode=interactive`
  console.log(`[WebSocket] Connecting to ${wsUrl}`)
  const ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'
  manager.setWs(port, ws)
  manager.setStatus(port, 'connecting')

  ws.onopen = async () => {
    if (manager.getSession(port)?.ws !== ws) {
      ws.close()
      return
    }
    console.log(`[WebSocket] Connected to port ${port}`)
    manager.setDisconnectReason(port, null)
    manager.setStatus(port, 'active')

    await manager.applyMeasuredFit(port, {
      propagate: true,
      force: true,
      reason: 'ws-open',
    })

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
        if (manager.getSession(port)?.terminalDisposed) {
          return
        }

        await manager.flushWrites(port)
        session.terminal.reset()
        if (payload.byteLength > 0) {
          manager.safeWrite(port, payload)
        }
        await manager.flushWrites(port)
        manager.refreshTerminalSurface(port)
        manager.resolveHistoryRefresh(port)
      } else if (header.type === 'output') {
        if (manager.getSession(port)?.terminalDisposed) {
          return
        }

        if (payload.byteLength > 0) {
          manager.safeWrite(port, payload)
        }
      } else if (header.type === 'title' && typeof header.title === 'string') {
        manager.updateSessionTitle(
          port,
          header.title,
          typeof header.title_updated_at === 'string' ? header.title_updated_at : null,
        )
      } else if (header.type === 'cwd' && typeof header.cwd === 'string') {
        manager.updateSessionCwd(port, header.cwd)
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

    if (currentSession.isRestoring) {
      manager.cancelHistoryRefresh(port)
    }

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
    if (manager.getSession(port)?.isRestoring) {
      manager.cancelHistoryRefresh(port)
    }
    manager.setDisconnectReason(port, 'WebSocket transport error')
    manager.setStatus(port, 'dead')
  }

  bindTerminalInput(port, ws)

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
