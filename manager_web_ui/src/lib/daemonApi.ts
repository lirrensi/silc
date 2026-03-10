function getPageProtocol(): string {
  return window.location.protocol === 'https:' ? 'https:' : 'http:'
}

function getPageHostname(): string {
  return window.location.hostname || '127.0.0.1'
}

export function getDaemonUrl(): string {
  return `${getPageProtocol()}//${getPageHostname()}:19999`
}

export function getSessionHttpUrl(port: number): string {
  return `${getPageProtocol()}//${getPageHostname()}:${port}`
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

export interface CreateSessionResponse {
  port: number
  session_id: string
  shell: string
}

export interface DaemonDefaults {
  cwd: string
  share_mode: boolean
  manager_url: string
}

export async function listSessions(): Promise<DaemonSession[]> {
  const resp = await fetch(`${getDaemonUrl()}/sessions`)
  if (!resp.ok) {
    throw new Error(`Failed to list sessions: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function getDefaults(): Promise<DaemonDefaults> {
  const resp = await fetch(`${getDaemonUrl()}/defaults`)
  if (!resp.ok) {
    throw new Error(`Failed to load defaults: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function createSession(options?: {
  port?: number
  shell?: string
  cwd?: string
}): Promise<CreateSessionResponse> {
  const resp = await fetch(`${getDaemonUrl()}/sessions`, {
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
  const resp = await fetch(`${getDaemonUrl()}/sessions/${port}/close`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to close session: HTTP ${resp.status}`)
  }
}

export async function killSession(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonUrl()}/sessions/${port}/kill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to kill session: HTTP ${resp.status}`)
  }
}

export async function restartSession(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonUrl()}/sessions/${port}/restart`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to restart session: HTTP ${resp.status}`)
  }
}

export async function resizeSession(port: number, rows: number, cols: number): Promise<void> {
  const url = `${getSessionHttpUrl(port)}/resize?rows=${rows}&cols=${cols}`
  const resp = await fetch(url, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to resize session: HTTP ${resp.status}`)
  }
}

export async function sendSigterm(port: number): Promise<void> {
  const resp = await fetch(`${getSessionHttpUrl(port)}/sigterm`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGTERM: HTTP ${resp.status}`)
  }
}

export async function sendSigkill(port: number): Promise<void> {
  const resp = await fetch(`${getSessionHttpUrl(port)}/sigkill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGKILL: HTTP ${resp.status}`)
  }
}

export async function sendInterrupt(port: number): Promise<void> {
  const resp = await fetch(`${getSessionHttpUrl(port)}/interrupt`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send interrupt: HTTP ${resp.status}`)
  }
}
