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
  console.log(`[DaemonAPI] GET ${DAEMON_URL}/sessions`)
  const resp = await fetch(`${DAEMON_URL}/sessions`)
  console.log(`[DaemonAPI] Response status: ${resp.status}`)
  if (!resp.ok) {
    const text = await resp.text()
    console.error(`[DaemonAPI] Error response:`, text)
    throw new Error(`Failed to list sessions: HTTP ${resp.status}`)
  }
  const data = await resp.json()
  console.log(`[DaemonAPI] Received ${data.length} sessions:`, data)
  return data
}

export async function createSession(options?: {
  port?: number
  shell?: string
  cwd?: string
}): Promise<CreateSessionResponse> {
  console.log(`[DaemonAPI] POST ${DAEMON_URL}/sessions`, options)
  const resp = await fetch(`${DAEMON_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options ?? {}),
  })
  console.log(`[DaemonAPI] Response status: ${resp.status}`)
  if (!resp.ok) {
    const text = await resp.text()
    console.error(`[DaemonAPI] Error response:`, text)
    throw new Error(`Failed to create session: HTTP ${resp.status}`)
  }
  const data = await resp.json()
  console.log(`[DaemonAPI] Created session:`, data)
  return data
}

export async function closeSession(port: number): Promise<void> {
  console.log(`[DaemonAPI] DELETE ${DAEMON_URL}/sessions/${port}`)
  const resp = await fetch(`${DAEMON_URL}/sessions/${port}`, { method: 'DELETE' })
  console.log(`[DaemonAPI] Response status: ${resp.status}`)
  if (!resp.ok) {
    const text = await resp.text()
    console.error(`[DaemonAPI] Error response:`, text)
    throw new Error(`Failed to close session: HTTP ${resp.status}`)
  }
  console.log(`[DaemonAPI] Session ${port} closed`)
}

export async function resizeSession(port: number, rows: number, cols: number): Promise<void> {
  const url = `http://127.0.0.1:${port}/resize?rows=${rows}&cols=${cols}`
  console.log(`[DaemonAPI] POST ${url}`)
  const resp = await fetch(url, { method: 'POST' })
  console.log(`[DaemonAPI] Response status: ${resp.status}`)
  if (!resp.ok) {
    const text = await resp.text()
    console.error(`[DaemonAPI] Error response:`, text)
    throw new Error(`Failed to resize session: HTTP ${resp.status}`)
  }
  console.log(`[DaemonAPI] Session ${port} resized to ${cols}x${rows}`)
}
