import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import type { Session, SessionStatus } from '@/types/session'

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
      status: 'idle',
      lastActivity: Date.now(),
    }

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
    if (!element) return

    if (element.parentNode) {
      element.remove()
    }

    container.appendChild(element)
    session.fitAddon.fit()
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
    setStatus,
    setWs,
  }
})
