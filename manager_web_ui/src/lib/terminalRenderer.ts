// FILE: manager_web_ui/src/lib/terminalRenderer.ts
// PURPOSE: Manage xterm renderer activation, fallback, and redraw recovery for frontend sessions.
// OWNS: WebGL renderer enablement, DOM fallback, and explicit redraw helpers.
// EXPORTS: enableRenderer - activates WebGL with fallback; disposeRenderer - tears down renderer state; refreshRendererAfterSwap - refreshes rows after renderer changes; forceTerminalRedraw - clears texture atlas and redraws.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import { WebglAddon } from '@xterm/addon-webgl'
import type { Session } from '@/types/session'

export async function enableRenderer(session: Session): Promise<void> {
  const terminal = session.terminal
  if (!terminal || !terminal.element || session.webglAddon) {
    return
  }

  let addon: WebglAddon | null = null

  try {
    addon = new WebglAddon()
    addon.onContextLoss(() => {
      disposeRenderer(session)
      session.rendererType = 'dom'
      session.rendererFailed = true
      refreshRendererAfterSwap(session)
    })
    terminal.loadAddon(addon)
    session.webglAddon = addon
    session.rendererType = 'webgl'
    session.rendererFailed = false
  } catch {
    addon?.dispose()
    session.webglAddon = null
    session.rendererType = 'dom'
    session.rendererFailed = true
  }
}

export function disposeRenderer(session: Session): void {
  try {
    session.webglAddon?.dispose()
  } catch {
    // Renderer cleanup is best-effort only.
  }
  session.webglAddon = null
  session.rendererType = 'dom'
}

export function refreshRendererAfterSwap(session: Session): void {
  try {
    const terminal = session.terminal
    if (!terminal) {
      return
    }

    if (terminal.rows > 0) {
      terminal.refresh(0, terminal.rows - 1)
    }
  } catch {
    // Ignore terminal repaint failures during teardown/recovery.
  }
}

export function forceTerminalRedraw(session: Session): void {
  try {
    session.terminal?.clearTextureAtlas?.()
  } catch {
    // Ignore terminal repaint failures during teardown/recovery.
  }

  refreshRendererAfterSwap(session)
}
