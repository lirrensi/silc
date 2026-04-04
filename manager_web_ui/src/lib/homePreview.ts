// FILE: manager_web_ui/src/lib/homePreview.ts
// PURPOSE: Fetch and cache frozen Home preview snapshots without taking over live session websockets.
// OWNS: One-shot snapshot retrieval, refresh throttling, and Home grid density helpers.
// EXPORTS: HOME_GRID_OPTIONS - supported Home grid densities; getHomeGridSlots - maps density to visible card count; getCachedHomePreviewSnapshot - reads the local snapshot cache; loadHomePreviewSnapshot - fetches a frozen session snapshot with throttling.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { getSessionHttpUrl } from '@/lib/daemonApi'
import { decodeWsFrame, requestHistoryFrame } from '@/lib/websocketFrame'

export type HomeGridDensity = '2x2' | '3x3' | '4x4'

export const HOME_GRID_OPTIONS: HomeGridDensity[] = ['2x2', '3x3', '4x4']

const SNAPSHOT_CACHE_TTL_MS = 2_500
const SNAPSHOT_QUEUE_GAP_MS = 140

const snapshotCache = new Map<number, { data: string; fetchedAt: number }>()
const inflightRequests = new Map<number, Promise<string>>()
let queueTail: Promise<void> = Promise.resolve()

export function getHomeGridSlots(density: HomeGridDensity): number {
  switch (density) {
    case '2x2':
      return 4
    case '4x4':
      return 16
    default:
      return 9
  }
}

export function getCachedHomePreviewSnapshot(port: number): string | null {
  const cached = snapshotCache.get(port)
  if (!cached) {
    return null
  }

  if (Date.now() - cached.fetchedAt > SNAPSHOT_CACHE_TTL_MS) {
    snapshotCache.delete(port)
    return null
  }

  return cached.data
}

export async function loadHomePreviewSnapshot(port: number, timeoutMs: number = 2500): Promise<string> {
  const cached = getCachedHomePreviewSnapshot(port)
  if (cached !== null) {
    return cached
  }

  const existing = inflightRequests.get(port)
  if (existing) {
    return existing
  }

  const request = enqueue(async () => {
    const snapshot = await requestSnapshot(port, timeoutMs)
    snapshotCache.set(port, { data: snapshot, fetchedAt: Date.now() })
    inflightRequests.delete(port)
    return snapshot
  }).catch((err) => {
    inflightRequests.delete(port)
    throw err
  })

  inflightRequests.set(port, request)
  return request
}

function enqueue<T>(job: () => Promise<T>): Promise<T> {
  const run = queueTail.then(async () => {
    const result = await job()
    await sleep(SNAPSHOT_QUEUE_GAP_MS)
    return result
  })

  queueTail = run.then(
    () => undefined,
    () => undefined,
  )

  return run
}

function requestSnapshot(port: number, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const wsUrl = `${getSessionHttpUrl(port).replace(/^http/, 'ws')}/ws`
    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    let settled = false
    let timer: number | null = null
    const textDecoder = new TextDecoder()

    const finish = (resolver: () => void): void => {
      if (settled) {
        return
      }

      settled = true
      if (timer !== null) {
        window.clearTimeout(timer)
      }
      try {
        ws.close()
      } catch {
        // Best-effort cleanup only.
      }
      resolver()
    }

    timer = window.setTimeout(() => {
      finish(() => reject(new Error(`Timed out waiting for preview snapshot on :${port}`)))
    }, timeoutMs)

    ws.onopen = () => {
      try {
        requestHistoryFrame(ws)
      } catch (err) {
        finish(() => reject(err instanceof Error ? err : new Error(String(err))))
      }
    }

    ws.onmessage = (event) => {
      try {
        if (!(event.data instanceof ArrayBuffer)) {
          throw new Error('Expected binary websocket frame')
        }

        const { header, payload } = decodeWsFrame(event.data)
        if (header.type === 'history') {
          finish(() => resolve(textDecoder.decode(payload)))
        }
      } catch (err) {
        finish(() => reject(err instanceof Error ? err : new Error(String(err))))
      }
    }

    ws.onerror = () => {
      finish(() => reject(new Error(`Failed to load preview snapshot for :${port}`)))
    }

    ws.onclose = () => {
      if (!settled) {
        finish(() => reject(new Error(`Preview snapshot websocket closed for :${port}`)))
      }
    }
  })
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
