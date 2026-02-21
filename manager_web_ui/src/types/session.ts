import type { Terminal } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'

export type SessionStatus = 'active' | 'idle' | 'dead'

export interface Session {
  port: number
  sessionId: string
  shell: string
  terminal: Terminal
  fitAddon: FitAddon
  ws: WebSocket | null
  status: SessionStatus
  lastActivity: number
}

export interface DaemonSession {
  port: number
  session_id: string
  shell: string
  idle_seconds: number
  alive: boolean
}
