// FILE: manager_web_ui/src/lib/terminalRenderer.ts
// PURPOSE: Manage xterm renderer activation, fallback, and redraw recovery for frontend sessions.
// OWNS: WebGL renderer enablement, DOM fallback, and explicit redraw helpers.
// EXPORTS: enableRenderer - activates WebGL with fallback; disposeRenderer - tears down renderer state; refreshRendererAfterSwap - refreshes rows after renderer changes; forceTerminalRedraw - clears texture atlas and redraws.
// DOCS: agent_chat/plan_web_terminal_fidelity_2026-04-04.md

import { WebglAddon } from '@xterm/addon-webgl'
import type { Session } from '@/types/session'

export async function enableRenderer(session: Session): Promise<void> {
  if (!session.terminal.element || session.webglAddon) {
    return
  }

  let addon: WebglAddon | null = null

  try {
    addon = new WebglAddon()
    session.terminal.loadAddon(addon)
    addon.onContextLoss(() => {
      disposeRenderer(session)
      session.rendererType = 'dom'
      session.rendererFailed = true
      refreshRendererAfterSwap(session)
    })
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
  session.webglAddon?.dispose()
  session.webglAddon = null
  session.rendererType = 'dom'
}

export function refreshRendererAfterSwap(session: Session): void {
  if (session.terminal.rows > 0) {
    session.terminal.refresh(0, session.terminal.rows - 1)
  }
}

export function forceTerminalRedraw(session: Session): void {
  session.terminal.clearTextureAtlas?.()
  refreshRendererAfterSwap(session)
}
