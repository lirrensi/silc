import { useTerminalManager } from '@/stores/terminalManager'
import { disconnectWebSocket, connectWebSocket } from './websocket'

const IDLE_TIMEOUT_MS = 10 * 60 * 1000 // 10 minutes
const MIN_SESSIONS_FOR_IDLE = 10
const CHECK_INTERVAL_MS = 60 * 1000 // Check every minute

let checkInterval: ReturnType<typeof setInterval> | null = null

export function startIdleManager(): void {
  if (checkInterval) return

  checkInterval = setInterval(() => {
    const manager = useTerminalManager()
    const sessions = manager.sessionList

    // Only apply idle disconnect if 10+ sessions
    if (sessions.length < MIN_SESSIONS_FOR_IDLE) {
      return
    }

    const now = Date.now()

    for (const session of sessions) {
      // Skip if already disconnected or dead
      if (session.status === 'idle' || session.status === 'dead') {
        continue
      }

      // Skip if this is the focused session
      if (manager.focusedPort === session.port) {
        continue
      }

      // Check if idle for too long
      const idleTime = now - session.lastActivity
      if (idleTime > IDLE_TIMEOUT_MS) {
        console.log(`Disconnecting idle session :${session.port}`)
        disconnectWebSocket(session.port)
      }
    }
  }, CHECK_INTERVAL_MS)
}

export function stopIdleManager(): void {
  if (checkInterval) {
    clearInterval(checkInterval)
    checkInterval = null
  }
}

export function reconnectIfNeeded(port: number): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) return

  // Update activity timestamp
  session.lastActivity = Date.now()

  // Reconnect if idle
  if (session.status === 'idle') {
    connectWebSocket(port)
  }
}
