const DAEMON_URL = 'http://127.0.0.1:19999'

export interface DaemonSession {
  port: number
  name: string
  session_id: string
  shell: string
  cwd: string | null
  idle_seconds: number
  alive: boolean
}

export interface CreateSessionResponse {
  port: number
  session_id: string
  shell: string
}

export async function listSessions(): Promise<DaemonSession[]> {
  const resp = await fetch(`${DAEMON_URL}/sessions`)
  if (!resp.ok) {
    throw new Error(`Failed to list sessions: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function createSession(options?: {
  port?: number
  shell?: string
  cwd?: string
}): Promise<CreateSessionResponse> {
  const resp = await fetch(`${DAEMON_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options ?? {}),
  })
  if (!resp.ok) {
    throw new Error(`Failed to create session: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function closeSession(port: number): Promise<void> {
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}`, { method: 'DELETE' })
  if (!resp.ok) {
    throw new Error(`Failed to close session: HTTP ${resp.status}`)
  }
}

export async function resizeSession(port: number, rows: number, cols: number): Promise<void> {
  const url = `http://127.0.0.1:${port}/resize?rows=${rows}&cols=${cols}`
  const resp = await fetch(url, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to resize session: HTTP ${resp.status}`)
  }
}

export async function sendSigterm(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/sigterm`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGTERM: HTTP ${resp.status}`)
  }
}

export async function sendSigkill(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/sigkill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGKILL: HTTP ${resp.status}`)
  }
}

export async function sendInterrupt(port: number): Promise<void> {
  const resp = await fetch(`http://127.0.0.1:${port}/interrupt`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send interrupt: HTTP ${resp.status}`)
  }
}
