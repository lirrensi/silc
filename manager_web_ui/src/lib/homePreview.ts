// FILE: manager_web_ui/src/lib/homePreview.ts
// PURPOSE: Fetch and cache frozen Home preview snapshots without taking over live session websockets.
// OWNS: One-shot snapshot retrieval, refresh throttling, and Home grid density helpers.
// EXPORTS: HOME_GRID_OPTIONS - supported Home grid densities; getHomeGridSlots - maps density to visible card count; getCachedHomePreviewSnapshot - reads the local snapshot cache; loadHomePreviewSnapshot - fetches a frozen session snapshot with throttling.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { getDaemonSessionUrl } from '@/lib/daemonApi'

export type HomeGridDensity = '2x2' | '3x3' | '4x4'

export const HOME_GRID_OPTIONS: HomeGridDensity[] = ['2x2', '3x3', '4x4']

const SNAPSHOT_CACHE_TTL_MS = 2_500
const SNAPSHOT_QUEUE_GAP_MS = 140

const snapshotCache = new Map<number, { data: Uint8Array; fetchedAt: number }>()
const inflightRequests = new Map<number, Promise<Uint8Array>>()
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

export function getCachedHomePreviewSnapshot(port: number): Uint8Array | null {
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

export async function loadHomePreviewSnapshot(
  port: number,
  timeoutMs: number = 2500,
): Promise<Uint8Array> {
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

async function requestSnapshot(port: number, timeoutMs: number): Promise<Uint8Array> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${getDaemonSessionUrl(port)}/snapshot`, {
      signal: controller.signal,
      cache: 'no-store',
      headers: { Accept: 'application/octet-stream' },
    })

    if (!response.ok) {
      throw new Error(`Failed to load preview snapshot for :${port} (${response.status})`)
    }

    return new Uint8Array(await response.arrayBuffer())
  } catch (err) {
    if (controller.signal.aborted) {
      throw new Error(`Timed out waiting for preview snapshot on :${port}`)
    }
    throw err instanceof Error ? err : new Error(String(err))
  } finally {
    window.clearTimeout(timer)
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}
