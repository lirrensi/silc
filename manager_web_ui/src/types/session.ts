import type { Terminal, IDisposable } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'
import type { WebglAddon } from '@xterm/addon-webgl'

// FILE: manager_web_ui/src/types/session.ts
// PURPOSE: Define shared manager session types for terminal lifecycle, renderer state, and daemon session metadata.
// OWNS: Type contracts for frontend terminal sessions.
// EXPORTS: Session - terminal session state shape; DaemonSession - daemon-reported session metadata; SessionStatus - lifecycle status union.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

export type SessionStatus = 'active' | 'connecting' | 'idle' | 'dead' | 'restarting'

export interface Session {
  port: number
  sessionId: string
  name: string
  title: string
  shell: string
  cwd: string | null
  titleUpdatedAt: string | null
  terminal: Terminal
  fitAddon: FitAddon
  ws: WebSocket | null
  onDataDisposable: IDisposable | null
  status: SessionStatus
  lastActivity: number
  // Buffered write queue for safe terminal writes
  writeQueue: string[]
  writePending: boolean
  writeInFlight: boolean
  flushWaiters: Array<() => void>
  lastSize: { rows: number; cols: number } | null
  lastMeasuredSize: { width: number; height: number; dpr: number } | null
  webglAddon: WebglAddon | null
  rendererType: 'dom' | 'webgl'
  rendererFailed: boolean
  attachEpoch: number
  fitPropagationEnabled: boolean
  pendingOpen: boolean
  pendingFitTimer: ReturnType<typeof setTimeout> | null
  pendingAnimationFrame: number | null
  disconnectReason: string | null
}

export interface DaemonSession {
  port: number
  name: string
  title: string
  session_id: string
  shell: string
  cwd: string | null
  title_updated_at: string | null
  idle_seconds: number
  alive: boolean
}
