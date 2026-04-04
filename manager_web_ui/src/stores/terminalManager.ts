import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import type { Session, SessionStatus, DaemonSession } from '@/types/session'
import { resizeSession } from '@/lib/daemonApi'
import { getTerminalTheme } from '@/lib/themes'
import type { ResolvedTheme } from '@/lib/themes'

const MAX_COLS = 256
const MAX_ROWS = 64

export const useTerminalManager = defineStore('terminalManager', () => {
  const sessions = ref<Map<number, Session>>(new Map())
  const focusedPort = ref<number | null>(null)
  const currentTheme = ref<ResolvedTheme>('dark')

  // Computed
  const sessionList = computed(() => {
    return Array.from(sessions.value.values()).sort((a, b) => a.port - b.port)
  })

  const focusedSession = computed(() => {
    if (focusedPort.value === null) return null
    return sessions.value.get(focusedPort.value) ?? null
  })

  const activeCount = computed(() => {
    return Array.from(sessions.value.values()).filter(s => s.status === 'active').length
  })

  // Actions
  function createSession(port: number, sessionId: string, shell: string, name: string = '', cwd: string | null = null): Session {
    const terminal = new Terminal({
      cols: 120,
      rows: 30,
      scrollback: 5000,
      convertEol: true,
      allowProposedApi: true,
      theme: getTerminalTheme(currentTheme.value),
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 15,
      lineHeight: 1.05,
      cursorBlink: true,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    // Unicode11 for proper emoji/CJK character width handling
    terminal.loadAddon(new Unicode11Addon())
    terminal.unicode.activeVersion = '11'

    const session: Session = {
      port,
      sessionId,
      name,
      shell,
      cwd,
      terminal,
      fitAddon,
      ws: null,
      onDataDisposable: null,
      status: 'idle',
      lastActivity: Date.now(),
      writeQueue: [],
      writePending: false,
      lastSize: null,
      disconnectReason: null,
    }

    // Handle special keys BEFORE xterm processes them
    terminal.attachCustomKeyEventHandler((event) => {
      if (event.type !== 'keydown') return true

      // Ctrl+Enter
      if (event.ctrlKey && event.key === 'Enter') {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          session.ws.send(JSON.stringify({ event: 'type', text: '\x1b[13;5u', nonewline: true }))
        }
        return false
      }

      // Shift+Enter
      if (event.shiftKey && event.key === 'Enter' && !event.ctrlKey) {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          session.ws.send(JSON.stringify({ event: 'type', text: '\x1b[13;2u', nonewline: true }))
        }
        return false
      }

      // Ctrl+V - paste clipboard directly to terminal via WebSocket
      // Return false to prevent xterm AND browser from doing anything
      if (event.ctrlKey && event.key === 'v' && !event.shiftKey && !event.altKey) {
        navigator.clipboard.readText().then(text => {
          if (session.ws && session.ws.readyState === WebSocket.OPEN) {
            session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
          }
        }).catch(() => {
          // Clipboard access denied - ignore silently
        })
        return false // CRITICAL: stops xterm + browser from handling this
      }

      return true
    })

    sessions.value.set(port, session)
    return session
  }

  function getSession(port: number): Session | undefined {
    return sessions.value.get(port)
  }

  function updateSessionMetadata(daemonSession: DaemonSession): void {
    const session = sessions.value.get(daemonSession.port)
    if (!session) return

    session.sessionId = daemonSession.session_id
    session.name = daemonSession.name
    session.shell = daemonSession.shell
    session.cwd = daemonSession.cwd
  }

  function removeSession(port: number): void {
    const session = sessions.value.get(port)
    if (session) {
      // Clean up DOM event handlers
      const element = session.terminal.element as HTMLElement & {
        _silcPasteHandler?: (e: Event) => void
        _silcKeydownHandler?: (e: KeyboardEvent) => void
        _silcPasteEventHandler?: (e: Event) => void
      }
      if (element) {
        if (element._silcPasteHandler) {
          element.removeEventListener('contextmenu', element._silcPasteHandler)
        }
        if (element._silcKeydownHandler) {
          element.removeEventListener('keydown', element._silcKeydownHandler, true)
        }
        if (element._silcPasteEventHandler) {
          element.removeEventListener('paste', element._silcPasteEventHandler, true)
        }
      }

      // Clean up WebSocket
      if (session.ws) {
        session.ws.close()
      }

      // Clean up terminal data listener
      if (session.onDataDisposable) {
        session.onDataDisposable.dispose()
      }

      // Dispose terminal (also cleans up addons and attachCustomKeyEventHandler)
      session.terminal.dispose()
      sessions.value.delete(port)
    }
  }

  function setFocused(port: number | null): void {
    focusedPort.value = port
    if (port !== null) {
      const session = sessions.value.get(port)
      if (session) {
        session.lastActivity = Date.now()
      }
    }
  }

  function attach(port: number, container: HTMLElement): void {
    const session = sessions.value.get(port)
    if (!session) return

    const element = session.terminal.element

    if (!element) {
      session.terminal.open(container)
      setupBrowserEventHandlers(session)
      fit(port)
      return
    }

    if (element.parentNode) {
      element.remove()
    }
    container.appendChild(element)
    setupBrowserEventHandlers(session)
    fit(port)
  }

  /**
   * Set up DOM-level event handlers to prevent browser interference
   * with our custom clipboard handling (Ctrl+C/V, right-click paste).
   */
  function setupBrowserEventHandlers(session: Session): void {
    const element = session.terminal.element
    if (!element) return

    const typedElement = element as HTMLElement & {
      _silcPasteHandler?: (e: Event) => void
      _silcKeydownHandler?: (e: KeyboardEvent) => void
      _silcPasteEventHandler?: (e: Event) => void
    }

    const helperTextarea = element.querySelector('.xterm-helper-textarea') as HTMLTextAreaElement | null
    if (helperTextarea) {
      helperTextarea.spellcheck = false
      helperTextarea.autocapitalize = 'off'
      helperTextarea.autocomplete = 'off'
      helperTextarea.setAttribute('autocorrect', 'off')
      helperTextarea.setAttribute('data-gramm', 'false')
      helperTextarea.setAttribute('data-gramm_editor', 'false')
      helperTextarea.setAttribute('data-enable-grammarly', 'false')
      helperTextarea.inputMode = 'text'
    }

    // Remove existing handlers if any
    if (typedElement._silcPasteHandler) {
      element.removeEventListener('contextmenu', typedElement._silcPasteHandler)
    }
    if (typedElement._silcKeydownHandler) {
      element.removeEventListener('keydown', typedElement._silcKeydownHandler, true)
    }
    if (typedElement._silcPasteEventHandler) {
      element.removeEventListener('paste', typedElement._silcPasteEventHandler, true)
    }

    // Right-click paste
    const pasteHandler = (e: Event) => {
      e.preventDefault()
      navigator.clipboard.readText().then(text => {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
        }
      }).catch(() => {
        // Clipboard access denied - ignore silently
      })
    }
    element.addEventListener('contextmenu', pasteHandler)
    typedElement._silcPasteHandler = pasteHandler

    // Prevent browser's native paste dialog
    const pasteEventHandler = (e: Event) => {
      e.preventDefault()
      e.stopPropagation()
    }
    element.addEventListener('paste', pasteEventHandler, true)
    typedElement._silcPasteEventHandler = pasteEventHandler

    // Block browser's native Ctrl+C/V handling at DOM level (capture phase)
    const keydownHandler = (e: KeyboardEvent) => {
      if (!e.ctrlKey) return

      // Ctrl+C with selection - block browser copy
      if (e.code === 'KeyC' && session.terminal.hasSelection()) {
        e.preventDefault()
        e.stopPropagation()
        navigator.clipboard.writeText(session.terminal.getSelection())
        session.terminal.clearSelection()
        return
      }

      // Ctrl+V - block browser paste dialog (we handle paste ourselves)
      if (e.code === 'KeyV' && !e.shiftKey && !e.altKey) {
        e.preventDefault()
        e.stopPropagation()
        navigator.clipboard.readText().then(text => {
          if (session.ws && session.ws.readyState === WebSocket.OPEN) {
            session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
          }
        }).catch(() => {
          // Clipboard access denied - ignore silently
        })
        return
      }
    }
    element.addEventListener('keydown', keydownHandler, true) // capture phase
    typedElement._silcKeydownHandler = keydownHandler
  }

  async function fit(port: number, options?: { propagate?: boolean }): Promise<void> {
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) return

    const shouldPropagate = options?.propagate ?? true
    session.fitAddon.fit()

    let cols = session.terminal.cols
    let rows = session.terminal.rows

    cols = Math.min(cols, MAX_COLS)
    rows = Math.min(rows, MAX_ROWS)

    if (session.terminal.cols !== cols || session.terminal.rows !== rows) {
      session.terminal.resize(cols, rows)
    }

    if (!shouldPropagate) {
      session.lastSize = { rows, cols }
      return
    }

    if (session.lastSize && session.lastSize.rows === rows && session.lastSize.cols === cols) {
      return
    }

    session.lastSize = { rows, cols }

    try {
      await resizeSession(port, rows, cols)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      if (message.includes('HTTP 410')) {
        setStatus(port, 'dead')
        return
      }
      console.error(`[TerminalManager] fit error for port ${port}:`, err)
    }
  }

  function detach(port: number): void {
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) return
    session.terminal.element.remove()
  }

  function setStatus(port: number, status: SessionStatus): void {
    const session = sessions.value.get(port)
    if (session) {
      session.status = status
      session.terminal.options.disableStdin = status !== 'active'
      if (status === 'active' || status === 'connecting' || status === 'restarting') {
        session.disconnectReason = null
      }
    }
  }

  function setDisconnectReason(port: number, reason: string | null): void {
    const session = sessions.value.get(port)
    if (session) {
      session.disconnectReason = reason
    }
  }

  function setWs(port: number, ws: WebSocket | null): void {
    const session = sessions.value.get(port)
    if (session) {
      session.ws = ws
    }
  }

  function reconcileSessions(daemonSessions: DaemonSession[]): void {
    const daemonPorts = new Set(daemonSessions.map(session => session.port))

    for (const daemonSession of daemonSessions) {
      if (!sessions.value.has(daemonSession.port)) {
        createSession(
          daemonSession.port,
          daemonSession.session_id,
          daemonSession.shell,
          daemonSession.name,
          daemonSession.cwd,
        )
      } else {
        updateSessionMetadata(daemonSession)
      }
    }

    for (const port of Array.from(sessions.value.keys())) {
      if (!daemonPorts.has(port)) {
        removeSession(port)
      }
    }
  }

  function applyTheme(theme: ResolvedTheme): void {
    currentTheme.value = theme
    const terminalTheme = getTerminalTheme(theme)

    for (const session of sessions.value.values()) {
      session.terminal.options.theme = terminalTheme
      session.terminal.refresh(0, session.terminal.rows - 1)
    }
  }

  /**
   * Safe buffered write to terminal.
   * Buffers writes and processes them sequentially with callback
   * to prevent escape sequence splitting across chunks.
   */
  function safeWrite(port: number, data: string): void {
    const session = sessions.value.get(port)
    if (!session) return

    session.writeQueue.push(data)

    if (!session.writePending) {
      processWriteQueue(port)
    }
  }

  function processWriteQueue(port: number): void {
    const session = sessions.value.get(port)
    if (!session || session.writeQueue.length === 0) {
      if (session) session.writePending = false
      return
    }

    session.writePending = true
    const combined = session.writeQueue.join('')
    session.writeQueue.length = 0

    session.terminal.write(combined, () => {
      // Check if more data arrived while we were writing
      if (session.writeQueue.length > 0) {
        processWriteQueue(port)
      } else {
        session.writePending = false
      }
    })
  }

  return {
    sessions,
    focusedPort,
    sessionList,
    focusedSession,
    activeCount,
    createSession,
    getSession,
    removeSession,
    setFocused,
    attach,
    detach,
    fit,
    setStatus,
    setDisconnectReason,
    setWs,
    reconcileSessions,
    safeWrite,
    applyTheme,
  }
})
