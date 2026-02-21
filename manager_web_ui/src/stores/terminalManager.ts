import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
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
    }

    // Handle Ctrl+Enter and other modified keys that xterm doesn't emit by default
    terminal.attachCustomKeyEventHandler((event) => {
      if (event.type === 'keydown') {
        // Helper to send via WebSocket
        const sendKey = (text: string) => {
          if (session.ws && session.ws.readyState === WebSocket.OPEN) {
            session.ws.send(JSON.stringify({ event: 'type', text, nonewline: true }))
          }
        }
        // Ctrl+Enter
        if (event.ctrlKey && event.key === 'Enter') {
          sendKey('\x1b[13;5u')
          event.preventDefault()
          return false
        }
        // Shift+Enter
        if (event.shiftKey && event.key === 'Enter' && !event.ctrlKey) {
          sendKey('\x1b[13;2u')
          event.preventDefault()
          return false
        }
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
      if (session.ws) {
        session.ws.close()
      }
      if (session.onDataDisposable) {
        session.onDataDisposable.dispose()
      }
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
      fit(port)
      return
    }

    if (element.parentNode) {
      element.remove()
    }
    container.appendChild(element)
    fit(port)
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
  }
})
