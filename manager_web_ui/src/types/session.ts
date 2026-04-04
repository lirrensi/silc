import type { Terminal, IDisposable } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'

export type SessionStatus = 'active' | 'connecting' | 'idle' | 'dead' | 'restarting'

export interface Session {
  port: number
  sessionId: string
  name: string
  shell: string
  cwd: string | null
  terminal: Terminal
  fitAddon: FitAddon
  ws: WebSocket | null
  onDataDisposable: IDisposable | null
  status: SessionStatus
  lastActivity: number
  // Buffered write queue for safe terminal writes
  writeQueue: string[]
  writePending: boolean
  lastSize: { rows: number; cols: number } | null
  disconnectReason: string | null
}

export interface DaemonSession {
  port: number
  name: string
  session_id: string
  shell: string
  cwd: string | null
  idle_seconds: number
  alive: boolean
}
