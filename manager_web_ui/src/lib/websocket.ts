// FILE: manager_web_ui/src/lib/websocket.ts
// PURPOSE: Connect session terminals to the daemon websocket while preserving ordered history and repaint recovery.
// OWNS: Websocket lifecycle for terminal sessions and history/output/title message handling.
// EXPORTS: connectWebSocket - open or replace a session websocket; disconnectWebSocket - close a session websocket intentionally.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { getSessionHttpUrl } from '@/lib/daemonApi'
import { decodeWsFrame, requestHistoryFrame, sendInputFrame } from '@/lib/websocketFrame'
import { useTerminalManager } from '@/stores/terminalManager'

export { decodeWsFrame, encodeWsFrame, requestHistoryFrame, sendInputFrame, sendWsFrame } from '@/lib/websocketFrame'

const SUPPRESSED_TERMINAL_INPUTS = new Set(['\x1b[c', '\x1b[0c', '\x1b[?1;2c'])

function logWebSocket(port: number, message: string, extra?: Record<string, unknown>): void {
  console.info('[WebSocket]', message, {
    port,
    ...extra,
  })
}

function bindTerminalInput(port: number, ws: WebSocket): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (!session) {
    logWebSocket(port, 'Early return: cannot bind terminal input because session is missing')
    return
  }

  if (session.terminalDisposed) {
    logWebSocket(port, 'Early return: terminal input binding skipped because terminal is disposed')
    return
  }

  const terminal = session.terminal
  if (!terminal) {
    logWebSocket(port, 'Early return: terminal input binding skipped because terminal is absent')
    return
  }

  session.onDataDisposable?.dispose()
  logWebSocket(port, 'Binding terminal input listener to websocket', {
    readyState: ws.readyState,
  })
  session.onDataDisposable = terminal.onData((data: string) => {
    if (SUPPRESSED_TERMINAL_INPUTS.has(data)) {
      logWebSocket(port, 'Suppressing terminal device-attributes probe', {
        input: JSON.stringify(data),
      })
      return
    }

    if (ws.readyState === WebSocket.OPEN) {
      logWebSocket(port, 'Forwarding terminal input frame to backend', {
        bytes: data.length,
      })
      sendInputFrame(ws, data)
      return
    }

    logWebSocket(port, 'Dropping terminal input because websocket is not open', {
      readyState: ws.readyState,
    })
  })
}

export function connectWebSocket(port: number, options?: { force?: boolean }): WebSocket | null {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  logWebSocket(port, 'connectWebSocket called', {
    force: options?.force === true,
    hasSession: Boolean(session),
  })

  if (!session) {
    console.error('[WebSocket] No session found for connect attempt', { port })
    return null
  }

  const existingWs = session.ws
  if (existingWs && !options?.force && (existingWs.readyState === WebSocket.OPEN || existingWs.readyState === WebSocket.CONNECTING)) {
    logWebSocket(port, 'Reusing existing websocket connection', {
      readyState: existingWs.readyState,
    })
    bindTerminalInput(port, existingWs)
    return existingWs
  }

  if (existingWs) {
    logWebSocket(port, 'Closing existing websocket before replacement', {
      readyState: existingWs.readyState,
      force: options?.force === true,
    })
    manager.setWs(port, null)
    existingWs.close()
  }

  const wsBase = getSessionHttpUrl(port).replace(/^http/, 'ws')
  const wsUrl = `${wsBase}/ws?mode=interactive`
  logWebSocket(port, 'Constructed websocket URL and starting connection attempt', {
    wsBase,
    wsUrl,
  })
  const ws = new WebSocket(wsUrl)
  ws.binaryType = 'arraybuffer'
  manager.setWs(port, ws)
  manager.setStatus(port, 'connecting')
  logWebSocket(port, 'Session status set to connecting')

  ws.onopen = async () => {
    if (manager.getSession(port)?.ws !== ws) {
      logWebSocket(port, 'Early return: websocket opened after being replaced; closing stale socket')
      ws.close()
      return
    }
    logWebSocket(port, 'Websocket open event received', {
      url: wsUrl,
    })
    manager.setDisconnectReason(port, null)
    manager.setStatus(port, 'active')

    await manager.applyMeasuredFit(port, {
      propagate: true,
      force: true,
      reason: 'ws-open',
    })

    logWebSocket(port, 'Requesting session history after websocket open')
    requestHistoryFrame(ws)
    manager.updateSessionTitle(port, session.title || '', session.titleUpdatedAt)
    manager.scheduleFit(port, { immediate: true, reason: 'ws-open' })
  }

  ws.onmessage = async (event) => {
    try {
      if (!(event.data instanceof ArrayBuffer)) {
        logWebSocket(port, 'Rejecting non-binary websocket message', {
          dataType: typeof event.data,
        })
        throw new Error('Expected binary websocket frame')
      }

      const { header, payload } = decodeWsFrame(event.data)
      logWebSocket(port, 'Received websocket frame', {
        type: String(header.type),
        bytes: payload.byteLength,
      })

      if (header.type === 'history') {
        if (manager.getSession(port)?.terminalDisposed) {
          logWebSocket(port, 'Early return: ignoring history frame because terminal is disposed')
          return
        }

        const terminal = session.terminal
        if (!terminal) {
          logWebSocket(port, 'Early return: ignoring history frame because terminal is missing')
          return
        }

        logWebSocket(port, 'Replaying history frame into terminal', {
          bytes: payload.byteLength,
        })
        await manager.flushWrites(port)
        terminal.reset()
        if (payload.byteLength > 0) {
          manager.safeWrite(port, payload)
        }
        await manager.flushWrites(port)
        manager.refreshTerminalSurface(port)
        manager.resolveHistoryRefresh(port)
        logWebSocket(port, 'History frame replay complete')
      } else if (header.type === 'output') {
        if (manager.getSession(port)?.terminalDisposed) {
          logWebSocket(port, 'Early return: ignoring output frame because terminal is disposed')
          return
        }

        if (payload.byteLength > 0) {
          logWebSocket(port, 'Appending output frame to terminal write queue', {
            bytes: payload.byteLength,
          })
          manager.safeWrite(port, payload)
          return
        }

        logWebSocket(port, 'Received empty output frame; nothing to append')
      } else if (header.type === 'title' && typeof header.title === 'string') {
        logWebSocket(port, 'Applying title frame', {
          title: header.title,
          titleUpdatedAt: typeof header.title_updated_at === 'string' ? header.title_updated_at : null,
        })
        manager.updateSessionTitle(
          port,
          header.title,
          typeof header.title_updated_at === 'string' ? header.title_updated_at : null,
        )
      } else if (header.type === 'cwd' && typeof header.cwd === 'string') {
        logWebSocket(port, 'Applying cwd frame', {
          cwd: header.cwd,
        })
        manager.updateSessionCwd(port, header.cwd)
      } else {
        logWebSocket(port, 'Rejecting unsupported websocket frame type', {
          type: String(header.type),
        })
        throw new Error(`Unsupported websocket frame type: ${String(header.type)}`)
      }
    } catch (err) {
      console.error(`[WebSocket] Frame handling failed for port ${port}:`, err)
      if (ws.readyState === WebSocket.OPEN) {
        ws.close(1002, 'Invalid websocket frame')
      }
    }
  }

  ws.onclose = (event) => {
    const currentSession = manager.getSession(port)
    if (!currentSession || currentSession.ws !== ws) {
      logWebSocket(port, 'Ignoring close event from stale websocket', {
        code: event.code,
        reason: event.reason,
      })
      return
    }
    logWebSocket(port, 'Websocket close event received', {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean,
      previousStatus: currentSession.status,
    })
    manager.setWs(port, null)

    if (currentSession.isRestoring) {
      logWebSocket(port, 'Cancelling in-flight history restore because websocket closed')
      manager.cancelHistoryRefresh(port)
    }

    if (currentSession.status === 'restarting') {
      logWebSocket(port, 'Close event observed during restart; preserving restarting status')
      return
    }

    manager.setDisconnectReason(port, event.reason || null)
    manager.setStatus(port, currentSession.status === 'connecting' ? 'dead' : 'idle')
  }

  ws.onerror = (err) => {
    if (manager.getSession(port)?.ws !== ws) {
      logWebSocket(port, 'Ignoring websocket error from stale socket')
      return
    }
    console.error(`[WebSocket] Error for port ${port}:`, err)
    if (manager.getSession(port)?.isRestoring) {
      logWebSocket(port, 'Cancelling in-flight history restore because websocket errored')
      manager.cancelHistoryRefresh(port)
    }
    manager.setDisconnectReason(port, 'WebSocket transport error')
    manager.setStatus(port, 'dead')
  }

  bindTerminalInput(port, ws)

  return ws
}

export function disconnectWebSocket(port: number): void {
  const manager = useTerminalManager()
  const session = manager.getSession(port)

  if (session?.ws) {
    logWebSocket(port, 'Disconnect requested by client code', {
      readyState: session.ws.readyState,
    })
    const ws = session.ws
    manager.setWs(port, null)
    manager.setDisconnectReason(port, null)
    manager.setStatus(port, 'idle')
    ws.close()
    return
  }

  logWebSocket(port, 'Disconnect requested but no websocket was attached')
}
