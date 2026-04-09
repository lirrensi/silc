// FILE: manager_web_ui/src/__tests__/daemonHttpRoutes.spec.ts
// PURPOSE: Verify daemon-routed session HTTP clients target the public daemon port.
// OWNS: HTTP client path coverage for session control and frozen snapshot fetches.
// DOCS: docs/spec.md

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  bulkSendSigtermSessions,
  clearSession,
  getDaemonSessionUrl,
  getSessionStatus,
  listSessions,
  resizeSession,
  sendInterrupt,
  sendSigkill,
  sendSigterm,
  unloadSession,
} from '@/lib/daemonApi'
import { loadHomePreviewSnapshot } from '@/lib/homePreview'

describe('daemon-routed session HTTP clients', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('builds daemon session URLs from the public daemon port', () => {
    expect(getDaemonSessionUrl(20000)).toContain(':19999/sessions/20000')
  })

  it('routes non-interactive control calls through the daemon', async () => {
    const fetchMock = vi.mocked(global.fetch)
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) } as Response)

    await resizeSession(20000, 24, 80)
    await sendInterrupt(20000)
    await sendSigterm(20000)
    await sendSigkill(20000)
    await clearSession(20000)
    await unloadSession(20000)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/resize?rows=24&cols=80'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/interrupt'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/sigterm'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/sigkill'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/clear'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/unload'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('fans out representative bulk commands through daemon session routes', async () => {
    const fetchMock = vi.mocked(global.fetch)
    fetchMock.mockResolvedValue({ ok: true, json: async () => ([{ port: 20000 }]) } as Response)

    await bulkSendSigtermSessions()

    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining('/sessions'))
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining('/sessions/20000/sigterm'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('loads frozen home previews from the daemon snapshot route', async () => {
    const snapshotBytes = new Uint8Array([1, 2, 3, 4])
    const fetchMock = vi.mocked(global.fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      arrayBuffer: async () => snapshotBytes.buffer,
    } as Response)

    const snapshot = await loadHomePreviewSnapshot(20000)

    expect(snapshot).toEqual(snapshotBytes)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/sessions/20000/snapshot'),
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('accepts command metadata in daemon session payloads', async () => {
    const fetchMock = vi.mocked(global.fetch)
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ([
        {
          port: 20000,
          name: 'alpha',
          title: 'Bash',
          session_id: 'sess-1',
          shell: 'bash',
          cwd: '/work/alpha',
          title_updated_at: null,
          command: { text: 'npm run dev', source: 'shell', start_ts: '2026-04-09T00:00:00Z' },
          idle_seconds: 0,
          alive: true,
          runtime_state: 'running',
          dormant: false,
        },
      ]),
    } as Response)

    const sessions = await listSessions()

    expect(sessions[0].command?.text).toBe('npm run dev')

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        port: 20000,
        name: 'alpha',
        title: 'Bash',
        session_id: 'sess-1',
        shell: 'bash',
        cwd: '/work/alpha',
        title_updated_at: null,
        command: { text: 'npm run dev', source: 'shell', start_ts: '2026-04-09T00:00:00Z' },
        idle_seconds: 0,
        alive: true,
        runtime_state: 'running',
        dormant: false,
      }),
    } as Response)

    const status = await getSessionStatus(20000)
    expect(status.command?.text).toBe('npm run dev')
  })
})
