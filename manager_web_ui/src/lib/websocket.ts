// FILE: manager_web_ui/src/lib/websocket.ts
// PURPOSE: Connect session terminals to the daemon websocket while preserving ordered history and repaint recovery.
// OWNS: Websocket lifecycle for terminal sessions and history/update message handling.
// EXPORTS: connectWebSocket - open or replace a session websocket; disconnectWebSocket - close a session websocket intentionally.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import { getSessionHttpUrl } from '@/lib/daemonApi'
import { useTerminalManager } from '@/stores/terminalManager'

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
    ws.send(JSON.stringify({ event: 'load_history' }))
    manager.scheduleFit(port, { immediate: true, reason: 'ws-open' })
  }

  ws.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data)

      if (msg.event === 'history' && msg.data) {
        await manager.flushWrites(port)
        session.terminal.clear()
        manager.safeWrite(port, msg.data)
        await manager.flushWrites(port)
        manager.refreshTerminalSurface(port)
      } else if (msg.event === 'update' && msg.data) {
        manager.safeWrite(port, msg.data)
      }
    } catch {
      manager.safeWrite(port, event.data)
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
      ws.send(JSON.stringify({ event: 'type', text: data, nonewline: true }))
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
