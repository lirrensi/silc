import { useTerminalManager } from '@/stores/terminalManager'

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

export function connectWebSocket(port: number): WebSocket | null {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) {
    console.error(`No session found for port ${port}`)
    return null
  }

  // Close existing connection if any
  if (session.ws) {
    session.ws.close()
  }

  const wsUrl = `${WS_PROTOCOL}//127.0.0.1:${port}/ws`
  const ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    manager.setStatus(port, 'active')
    manager.setWs(port, ws)

    // Request terminal history
    ws.send(JSON.stringify({ event: 'load_history' }))
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)

      if (msg.event === 'history' && msg.data) {
        session.terminal.clear()
        session.terminal.write(msg.data)
      } else if (msg.event === 'update' && msg.data) {
        session.terminal.write(msg.data)
      }
    } catch {
      // Raw text output
      session.terminal.write(event.data)
    }
  }

  ws.onclose = () => {
    manager.setStatus(port, 'idle')
    manager.setWs(port, null)
  }

  ws.onerror = (err) => {
    console.error(`WebSocket error for port ${port}:`, err)
    manager.setStatus(port, 'dead')
  }

  // Wire up terminal input to WebSocket
  session.terminal.onData((data: string) => {
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
    session.ws.close()
    manager.setWs(port, null)
    manager.setStatus(port, 'idle')
  }
}
