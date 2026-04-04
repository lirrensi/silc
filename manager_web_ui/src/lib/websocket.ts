import { useTerminalManager } from '@/stores/terminalManager'
import { getSessionHttpUrl } from '@/lib/daemonApi'

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

    // Request terminal history
    ws.send(JSON.stringify({ event: 'load_history' }))
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)

      if (msg.event === 'history' && msg.data) {
        session.terminal.clear()
        manager.safeWrite(port, msg.data)
      } else if (msg.event === 'update' && msg.data) {
        manager.safeWrite(port, msg.data)
      }
    } catch {
      // Raw text output
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

  // Wire up terminal input to WebSocket
  // Dispose old handler if exists
  if (session.onDataDisposable) {
    session.onDataDisposable.dispose()
  }

  // Register new handler and store disposable
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
