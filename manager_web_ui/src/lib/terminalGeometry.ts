// FILE: manager_web_ui/src/lib/terminalGeometry.ts
// PURPOSE: Measure renderable terminal containers and derive stable xterm geometry proposals.
// OWNS: Frontend-only terminal visibility checks and resize geometry calculations.
// EXPORTS: isElementRenderable - checks visible host readiness; measureContainer - captures container pixels and DPR; proposeTerminalGeometry - derives clamped rows and cols; hasGeometryChanged - compares geometry snapshots.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import type { FitAddon } from '@xterm/addon-fit'
import type { Terminal } from '@xterm/xterm'

export interface MeasuredContainerSize {
  width: number
  height: number
  dpr: number
}

export interface TerminalGeometry extends MeasuredContainerSize {
  cols: number
  rows: number
}

export function isElementRenderable(element: HTMLElement | null): boolean {
  if (!element || !element.isConnected) {
    return false
  }

  const rect = element.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) {
    return false
  }

  const style = window.getComputedStyle(element)
  return style.display !== 'none' && style.visibility !== 'hidden'
}

export function measureContainer(element: HTMLElement): MeasuredContainerSize {
  const rect = element.getBoundingClientRect()

  return {
    width: rect.width,
    height: rect.height,
    dpr: window.devicePixelRatio || 1,
  }
}

export function proposeTerminalGeometry(
  terminal: Terminal,
  fitAddon: FitAddon,
  element: HTMLElement,
  limits: { maxCols: number; maxRows: number },
): TerminalGeometry | null {
  if (!isElementRenderable(element)) {
    return null
  }

  const proposed = fitAddon.proposeDimensions()
  if (!proposed?.cols || !proposed?.rows) {
    return null
  }

  const measured = measureContainer(element)

  return {
    cols: Math.max(2, Math.min(proposed.cols, limits.maxCols)),
    rows: Math.max(1, Math.min(proposed.rows, limits.maxRows)),
    width: measured.width,
    height: measured.height,
    dpr: measured.dpr,
  }
}

export function hasGeometryChanged(
  previous: TerminalGeometry | null,
  next: TerminalGeometry,
): boolean {
  if (!previous) {
    return true
  }

  return (
    previous.cols !== next.cols
    || previous.rows !== next.rows
    || previous.width !== next.width
    || previous.height !== next.height
    || previous.dpr !== next.dpr
  )
}
