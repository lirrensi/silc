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
  function createSession(port: number, sessionId: string, shell: string): Session {
    console.log(`[TerminalManager] Creating session: port=${port}, sessionId=${sessionId}, shell=${shell}`)
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
      shell,
      terminal,
      fitAddon,
      ws: null,
      onDataDisposable: null,
      status: 'idle',
      lastActivity: Date.now(),
    }

    sessions.value.set(port, session)
    console.log(`[TerminalManager] Session created successfully: port=${port}`)
    return session
  }

  function getSession(port: number): Session | undefined {
    const session = sessions.value.get(port)
    console.log(`[TerminalManager] getSession(${port}): ${session ? 'found' : 'not found'}`)
    return session
  }

  function removeSession(port: number): void {
    console.log(`[TerminalManager] removeSession(${port})`)
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
    console.log(`[TerminalManager] setFocused(${port})`)
    focusedPort.value = port
    if (port !== null) {
      const session = sessions.value.get(port)
      if (session) {
        session.lastActivity = Date.now()
      }
    }
  }

  function attach(port: number, container: HTMLElement): void {
    console.log(`[TerminalManager] attach(${port}, container)`)
    const session = sessions.value.get(port)
    if (!session) {
      console.warn(`[TerminalManager] attach: no session for port ${port}`)
      return
    }

    const element = session.terminal.element

    if (!element) {
      // Terminal hasn't been opened yet - open it on the container
      console.log(`[TerminalManager] Opening terminal on container for port ${port}`)
      session.terminal.open(container)
      console.log(`[TerminalManager] Terminal opened for port ${port}`)
      // Fit after open
      fit(port)
      return
    }

    // Terminal already open - move it to new container
    console.log(`[TerminalManager] Moving existing terminal to new container for port ${port}`)
    if (element.parentNode) {
      element.remove()
    }

    container.appendChild(element)
    fit(port)
  }

  async function fit(port: number): Promise<void> {
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) {
      console.warn(`[TerminalManager] fit: no session/terminal for port ${port}`)
      return
    }

    // Use FitAddon to calculate optimal dimensions
    session.fitAddon.fit()

    // Get dimensions from terminal after fit
    let cols = session.terminal.cols
    let rows = session.terminal.rows

    // Clamp to max
    cols = Math.min(cols, MAX_COLS)
    rows = Math.min(rows, MAX_ROWS)

    console.log(`[TerminalManager] fit(${port}): cols=${cols}, rows=${rows}`)

    // Resize terminal locally
    if (session.terminal.cols !== cols || session.terminal.rows !== rows) {
      session.terminal.resize(cols, rows)
    }

    // Notify backend
    try {
      await resizeSession(port, rows, cols)
    } catch (err) {
      console.error(`[TerminalManager] fit: failed to resize backend for port ${port}:`, err)
    }
  }

  function detach(port: number): void {
    console.log(`[TerminalManager] detach(${port})`)
    const session = sessions.value.get(port)
    if (!session?.terminal?.element) return

    session.terminal.element.remove()
  }

  function setStatus(port: number, status: SessionStatus): void {
    console.log(`[TerminalManager] setStatus(${port}, '${status}')`)
    const session = sessions.value.get(port)
    if (session) {
      session.status = status
    }
  }

  function setWs(port: number, ws: WebSocket | null): void {
    console.log(`[TerminalManager] setWs(${port}, ${ws ? 'WebSocket' : 'null'})`)
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
