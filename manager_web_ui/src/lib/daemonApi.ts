// FILE: manager_web_ui/src/lib/daemonApi.ts
// PURPOSE: Call daemon HTTP endpoints and define the stable daemon session and settings payload shapes used by the manager UI.
// OWNS: Daemon base URL helpers, HTTP API calls, and daemon response interfaces.
// EXPORTS: getDaemonUrl, getSessionHttpUrl, getDaemonSessionUrl, listSessions, createSession, closeSession, killSession, restartSession, renameSession, reorderSessions, getDefaults, getSettings, updateSettings, resizeSession, sendInterrupt, sendSigterm, sendSigkill, getSessionStatus, getSessionOutput, getSessionRawOutput, getSessionSnapshot, getSessionLogs, sendSessionInput, runSessionCommand, clearSession, resetSession.
// DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md

import type { ThemePresetName } from '@/lib/themePresets'

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

export function getDaemonSessionUrl(port: number): string {
  return `${getDaemonUrl()}/sessions/${port}`
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
  runtime_state: string | null
  dormant: boolean
}

export interface CreateSessionResponse {
  port: number
  name: string
  title: string
  session_id: string
  shell: string
}

export interface DaemonDefaults {
  cwd: string
  share_mode: boolean
  manager_url: string
  shell: string
  shell_options: DaemonShellOption[]
}

export interface DaemonUiSettings {
  managerTheme?: ThemePresetName
  themePreference?: 'light' | 'dark' | 'system'
}

export interface DaemonTerminalSettings {
  themePreset?: ThemePresetName
  theme?: 'light' | 'dark'
  cols?: number
  rows?: number
  scrollback?: number
  fontFamily?: string
  fontSize?: number
  lineHeight?: number
  cursorBlink?: boolean
}

export interface DaemonSettings {
  ui?: DaemonUiSettings
  terminal?: DaemonTerminalSettings
}

export interface DaemonShellOption {
  type: string
  label: string
  path: string
}

export interface RestartSessionResponse {
  status: string
  port: number
  name: string
  title: string
  shell: string
}

export interface RenameSessionResponse {
  port: number
  name: string
  title: string
  session_id: string
  shell: string
  cwd: string | null
  title_updated_at: string | null
  idle_seconds: number
  alive: boolean
  runtime_state: string | null
  dormant: boolean
}

export interface ReorderSessionResponse {
  sessions: DaemonSession[]
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

export async function getSettings(): Promise<DaemonSettings> {
  const resp = await fetch(`${getDaemonUrl()}/settings`)
  if (!resp.ok) {
    throw new Error(`Failed to load settings: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function updateSettings(update: Record<string, unknown>): Promise<DaemonSettings> {
  const resp = await fetch(`${getDaemonUrl()}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
  if (!resp.ok) {
    throw new Error(`Failed to update settings: HTTP ${resp.status}`)
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

export async function restartSession(port: number): Promise<RestartSessionResponse> {
  const resp = await fetch(`${getDaemonUrl()}/sessions/${port}/restart`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to restart session: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function renameSession(port: number, name: string): Promise<RenameSessionResponse> {
  const resp = await fetch(`${getDaemonUrl()}/sessions/${port}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!resp.ok) {
    throw new Error(`Failed to rename session: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function reorderSessions(ports: number[]): Promise<ReorderSessionResponse> {
  const resp = await fetch(`${getDaemonUrl()}/sessions/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ports }),
  })
  if (!resp.ok) {
    throw new Error(`Failed to reorder sessions: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function getSessionStatus(port: number): Promise<DaemonSession> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/status`)
  if (!resp.ok) {
    throw new Error(`Failed to load session status: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function getSessionOutput(port: number, lines: number = 100): Promise<{ output: string; lines: number }> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/out?lines=${lines}`)
  if (!resp.ok) {
    throw new Error(`Failed to load session output: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function getSessionRawOutput(port: number, lines: number = 100): Promise<{ output: string; lines: number }> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/raw?lines=${lines}`)
  if (!resp.ok) {
    throw new Error(`Failed to load session raw output: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function getSessionSnapshot(port: number): Promise<Uint8Array> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/snapshot`, {
    headers: { Accept: 'application/octet-stream' },
  })
  if (!resp.ok) {
    throw new Error(`Failed to load session snapshot: HTTP ${resp.status}`)
  }
  return new Uint8Array(await resp.arrayBuffer())
}

export async function getSessionLogs(port: number, tail: number = 100): Promise<{ logs: string; lines: number }> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/logs?tail=${tail}`)
  if (!resp.ok) {
    throw new Error(`Failed to load session logs: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function sendSessionInput(port: number, text: string, nonewline: boolean = false): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/in?nonewline=${nonewline ? 'true' : 'false'}`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    body: text,
  })
  if (!resp.ok) {
    throw new Error(`Failed to send session input: HTTP ${resp.status}`)
  }
}

export async function runSessionCommand(
  port: number,
  command: string,
  timeout: number = 60,
): Promise<{ output: string; exit_code?: number; status: string; error?: string; running_cmd?: string }> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/run?timeout=${timeout}`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    body: command,
  })
  if (!resp.ok) {
    throw new Error(`Failed to run session command: HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function clearSession(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/clear`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to clear session: HTTP ${resp.status}`)
  }
}

export async function resetSession(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/reset`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to reset session: HTTP ${resp.status}`)
  }
}

export async function resizeSession(port: number, rows: number, cols: number): Promise<void> {
  const url = `${getDaemonSessionUrl(port)}/resize?rows=${rows}&cols=${cols}`
  const resp = await fetch(url, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to resize session: HTTP ${resp.status}`)
  }
}

export async function sendSigterm(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/sigterm`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGTERM: HTTP ${resp.status}`)
  }
}

export async function sendSigkill(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/sigkill`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send SIGKILL: HTTP ${resp.status}`)
  }
}

export async function sendInterrupt(port: number): Promise<void> {
  const resp = await fetch(`${getDaemonSessionUrl(port)}/interrupt`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`Failed to send interrupt: HTTP ${resp.status}`)
  }
}
