import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import type { Session, SessionStatus } from '@/types/session'
import { resizeSession } from '@/lib/daemonApi'

const MAX_COLS = 256
const MAX_ROWS = 64

export const useTerminalManager = defineStore('terminalManager', () => {
  const sessions = ref<Map<number, Session>>(new Map())
  const focusedPort = ref<number | null>(null)

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
      theme: {
        background: '#1e1e1e',
        foreground: '#ffffff',
        cursor: '#ff80bf',
        selectionBackground: '#ff80bf44',
      },
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 15,
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
    }

    // Handle Ctrl+Enter and Shift+Enter (keys xterm doesn't emit by default)
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

      return true
    })

    sessions.value.set(port, session)
    return session
  }

  function getSession(port: number): Session | undefined {
    return sessions.value.get(port)
  }

  function removeSession(port: number): void {
    const session = sessions.value.get(port)
    if (session) {
      // Clean up DOM event handlers
      const element = session.terminal.element as HTMLElement & {
        _silcPasteHandler?: (e: Event) => void
        _silcKeydownHandler?: (e: KeyboardEvent) => void
      }
      if (element) {
        if (element._silcPasteHandler) {
          element.removeEventListener('contextmenu', element._silcPasteHandler)
        }
        if (element._silcKeydownHandler) {
          element.removeEventListener('keydown', element._silcKeydownHandler, true)
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
    }

    // Remove existing handlers if any
    if (typedElement._silcPasteHandler) {
      element.removeEventListener('contextmenu', typedElement._silcPasteHandler)
    }
    if (typedElement._silcKeydownHandler) {
      element.removeEventListener('keydown', typedElement._silcKeydownHandler)
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

    // Block browser's native Ctrl+C/V handling at DOM level
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

      // Ctrl+V - block browser paste (we handle it in attachCustomKeyEventHandler)
      if (e.code === 'KeyV') {
        e.preventDefault()
        e.stopPropagation()
        navigator.clipboard.readText().then(text => {
          if (session.ws && session.ws.readyState === WebSocket.OPEN) {
            session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
          }
        }).catch(() => {
          // Clipboard access denied - ignore silently
        })
      }
    }
    element.addEventListener('keydown', keydownHandler, true) // capture phase
    typedElement._silcKeydownHandler = keydownHandler
  }

  async function fit(port: number): Promise<void> {
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) return

    session.fitAddon.fit()

    let cols = session.terminal.cols
    let rows = session.terminal.rows

    cols = Math.min(cols, MAX_COLS)
    rows = Math.min(rows, MAX_ROWS)

    if (session.terminal.cols !== cols || session.terminal.rows !== rows) {
      session.terminal.resize(cols, rows)
    }

    try {
      await resizeSession(port, rows, cols)
      if (session.ws && session.ws.readyState === WebSocket.OPEN) {
        session.ws.send(JSON.stringify({ event: 'load_history' }))
      }
    } catch (err) {
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
    }
  }

  function setWs(port: number, ws: WebSocket | null): void {
    const session = sessions.value.get(port)
    if (session) {
      session.ws = ws
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
    setWs,
    safeWrite,
  }
})
