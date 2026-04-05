// FILE: manager_web_ui/src/stores/terminalManager.ts
// PURPOSE: Manage frontend terminal session lifecycle, visible-first attachment, measured resize, and recovery actions.
// OWNS: Browser terminal instances, resize propagation, write buffering, and renderer lifecycle.
// EXPORTS: useTerminalManager - Pinia store for terminal session state and actions including session ordering.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { FitAddon } from '@xterm/addon-fit'
import type { WebglAddon } from '@xterm/addon-webgl'
import { Unicode11Addon } from '@xterm/addon-unicode11'
import { Terminal } from '@xterm/xterm'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { resizeSession } from '@/lib/daemonApi'
import {
  hasGeometryChanged,
  isElementRenderable,
  proposeTerminalGeometry,
  type TerminalGeometry,
} from '@/lib/terminalGeometry'
import {
  disposeRenderer,
  enableRenderer,
  forceTerminalRedraw,
  refreshRendererAfterSwap,
} from '@/lib/terminalRenderer'
import { getTerminalTheme } from '@/lib/themes'
import type { ResolvedTheme } from '@/lib/themes'
import { sendInputFrame } from '@/lib/websocketFrame'
import type { DaemonSession, Session, SessionStatus } from '@/types/session'

const MAX_COLS = 256
const MAX_ROWS = 64
const FIT_DEBOUNCE_MS = 24

type RendererType = Session['rendererType']

export const useTerminalManager = defineStore('terminalManager', () => {
  const sessions = ref<Map<number, Session>>(new Map())
  const focusedPort = ref<number | null>(null)
  const currentTheme = ref<ResolvedTheme>('dark')
  const lastAppliedRendererType = new Map<number, RendererType>()
  const historyRefreshWaiters = new Map<number, Array<() => void>>()

  function createManagedTerminal(theme: ResolvedTheme): {
    terminal: Terminal
    fitAddon: FitAddon
  } {
    const terminal = new Terminal({
      cols: 120,
      rows: 30,
      scrollback: 5000,
      convertEol: true,
      allowProposedApi: true,
      theme: getTerminalTheme(theme),
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: 15,
      lineHeight: 1.05,
      cursorBlink: true,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(new Unicode11Addon())
    terminal.unicode.activeVersion = '11'

    return { terminal, fitAddon }
  }

  function attachSessionKeyHandlers(session: Session): void {
    session.terminal.attachCustomKeyEventHandler((event) => {
      if (event.type !== 'keydown') return true

      if (event.ctrlKey && event.key === 'Enter') {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          sendInputFrame(session.ws, '\x1b[13;5u')
        }
        return false
      }

      if (event.shiftKey && event.key === 'Enter' && !event.ctrlKey) {
        if (session.ws && session.ws.readyState === WebSocket.OPEN) {
          sendInputFrame(session.ws, '\x1b[13;2u')
        }
        return false
      }

      if (event.ctrlKey && event.key === 'c' && session.terminal.hasSelection()) {
        navigator.clipboard.writeText(session.terminal.getSelection())
        session.terminal.clearSelection()
        return false
      }

      if (event.ctrlKey && event.key === 'v' && !event.shiftKey && !event.altKey) {
        void pasteClipboardText(session.port)
        return false
      }

      return true
    })
  }

  function initializeSessionTerminal(session: Session): void {
    const { terminal, fitAddon } = createManagedTerminal(currentTheme.value)
    session.terminal = terminal
    session.fitAddon = fitAddon
    session.terminalDisposed = false
    attachSessionKeyHandlers(session)
  }

  const sessionList = computed(() => {
    return Array.from(sessions.value.values())
  })

  const focusedSession = computed(() => {
    if (focusedPort.value === null) return null
    return sessions.value.get(focusedPort.value) ?? null
  })

  const activeCount = computed(() => {
    return Array.from(sessions.value.values()).filter(s => s.status === 'active').length
  })

  async function pasteClipboardText(port: number): Promise<void> {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    try {
      const text = await navigator.clipboard.readText()
      if (text && session.ws && session.ws.readyState === WebSocket.OPEN) {
        sendInputFrame(session.ws, text)
      }
    } catch {
      // Clipboard access denied - ignore silently
    }
  }

  function createSession(
    port: number,
    sessionId: string,
    shell: string,
    name: string = '',
    cwd: string | null = null,
    title: string = '',
    titleUpdatedAt: string | null = null,
  ): Session {
    const session: Session = {
      port,
      sessionId,
      name,
      title,
      shell,
      cwd,
      titleUpdatedAt,
      terminal: null as unknown as Terminal,
      fitAddon: null as unknown as FitAddon,
      ws: null,
      onDataDisposable: null,
      status: 'idle',
      lastActivity: Date.now(),
      writeQueue: [],
      writePending: false,
      writeInFlight: false,
      flushWaiters: [],
      lastSize: null,
      lastMeasuredSize: null,
      webglAddon: null as WebglAddon | null,
      rendererType: 'dom',
      rendererFailed: false,
      terminalDisposed: false,
      isRestoring: false,
      attachEpoch: 0,
      fitPropagationEnabled: true,
      pendingOpen: false,
      pendingFitTimer: null,
      pendingAnimationFrame: null,
      disconnectReason: null,
    }

    initializeSessionTerminal(session)

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
    session.title = daemonSession.title
    session.shell = daemonSession.shell
    session.cwd = daemonSession.cwd
    session.titleUpdatedAt = daemonSession.title_updated_at
  }

  function upsertDaemonSession(daemonSession: DaemonSession): Session {
    const existingSession = sessions.value.get(daemonSession.port)
    if (!existingSession) {
      return createSession(
        daemonSession.port,
        daemonSession.session_id,
        daemonSession.shell,
        daemonSession.name,
        daemonSession.cwd,
        daemonSession.title,
        daemonSession.title_updated_at,
      )
    }

    updateSessionMetadata(daemonSession)
    return existingSession
  }

  function updateSessionTitle(port: number, title: string, titleUpdatedAt: string | null): void {
    const session = sessions.value.get(port)
    if (!session) return

    session.title = title
    session.titleUpdatedAt = titleUpdatedAt
  }

  function updateSessionCwd(port: number, cwd: string | null): void {
    const session = sessions.value.get(port)
    if (!session) return

    session.cwd = cwd
  }

  function clearPendingLayoutWork(session: Session): void {
    if (session.pendingFitTimer !== null) {
      clearTimeout(session.pendingFitTimer)
      session.pendingFitTimer = null
    }

    if (session.pendingAnimationFrame !== null) {
      cancelAnimationFrame(session.pendingAnimationFrame)
      session.pendingAnimationFrame = null
    }
  }

  function cleanupBrowserEventHandlers(session: Session): void {
    const element = session.terminal.element as HTMLElement & {
      _silcBrowserEventTarget?: EventTarget | null
      _silcDocumentContextMenuHandler?: (e: MouseEvent) => void
      _silcDocumentMouseDownHandler?: (e: MouseEvent) => void
      _silcContextMenuHandler?: (e: MouseEvent) => void
      _silcMouseDownHandler?: (e: MouseEvent) => void
      _silcPasteEventHandler?: (e: Event) => void
    }

    if (!element) {
      return
    }

    const browserEventTarget = element._silcBrowserEventTarget
    const ownerDocument = element.ownerDocument

    if (element._silcDocumentContextMenuHandler) {
      ownerDocument.removeEventListener('contextmenu', element._silcDocumentContextMenuHandler as EventListener, true)
    }
    if (element._silcDocumentMouseDownHandler) {
      ownerDocument.removeEventListener('mousedown', element._silcDocumentMouseDownHandler as EventListener, true)
    }

    if (browserEventTarget && element._silcContextMenuHandler) {
      browserEventTarget.removeEventListener('contextmenu', element._silcContextMenuHandler as EventListener, true)
    }
    if (browserEventTarget && element._silcMouseDownHandler) {
      browserEventTarget.removeEventListener('mousedown', element._silcMouseDownHandler as EventListener, true)
    }
    if (browserEventTarget && element._silcPasteEventHandler) {
      browserEventTarget.removeEventListener('paste', element._silcPasteEventHandler as EventListener, true)
    }

    element._silcBrowserEventTarget = null
    element._silcDocumentContextMenuHandler = undefined
    element._silcDocumentMouseDownHandler = undefined
  }

  function disposeSessionTerminal(session: Session): void {
    try {
      clearPendingLayoutWork(session)
    } catch {
      // best-effort
    }

    try {
      cleanupBrowserEventHandlers(session)
    } catch {
      // best-effort
    }

    try {
      disposeRenderer(session)
    } catch {
      // best-effort
    }

    session.pendingOpen = false
    session.isRestoring = false

    try {
      session.onDataDisposable?.dispose()
    } catch {
      // best-effort
    }
    session.onDataDisposable = null

    session.writeQueue = []
    session.writePending = false
    session.writeInFlight = false

    try {
      resolveFlushWaiters(session)
    } catch {
      // best-effort
    }

    try {
      session.terminal.dispose()
    } catch {
      // best-effort
    }

    session.terminalDisposed = true
  }

  function resolveFlushWaiters(session: Session): void {
    if (session.writePending || session.writeInFlight || session.writeQueue.length > 0) {
      return
    }

    const waiters = session.flushWaiters.splice(0, session.flushWaiters.length)
    for (const resolve of waiters) {
      resolve()
    }
  }

  async function openWhenRenderable(
    port: number,
    container: HTMLElement,
    options?: { propagate?: boolean },
  ): Promise<void> {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    session.fitPropagationEnabled = options?.propagate ?? session.fitPropagationEnabled

    session.attachEpoch += 1
    const epoch = session.attachEpoch

    if (session.terminal.element) {
      setupBrowserEventHandlers(session)
      scheduleFit(port, {
        immediate: true,
        reason: 'reattach-existing-open',
        force: options?.propagate === true,
      })
      return
    }

    session.pendingOpen = true
    clearPendingLayoutWork(session)

    await new Promise<void>((resolve) => {
      const retry = () => {
        const currentSession = sessions.value.get(port)
        if (!currentSession || currentSession.attachEpoch !== epoch) {
          resolve()
          return
        }

        if (currentSession.terminal.element || isElementRenderable(container)) {
          clearPendingLayoutWork(currentSession)
          resolve()
          return
        }

        currentSession.pendingAnimationFrame = requestAnimationFrame(() => {
          currentSession.pendingAnimationFrame = null
          retry()
        })

        currentSession.pendingFitTimer = setTimeout(() => {
          if (currentSession.pendingAnimationFrame !== null) {
            cancelAnimationFrame(currentSession.pendingAnimationFrame)
            currentSession.pendingAnimationFrame = null
          }
          retry()
        }, FIT_DEBOUNCE_MS)
      }

      retry()
    })

    const currentSession = sessions.value.get(port)
    if (!currentSession || currentSession.attachEpoch !== epoch) {
      return
    }

    currentSession.pendingOpen = false

    if (currentSession.terminal.element || !isElementRenderable(container)) {
      return
    }

    currentSession.terminal.open(container)
    setupBrowserEventHandlers(currentSession)

    await enableRenderer(currentSession)
    scheduleFit(port, {
      immediate: true,
      reason: 'initial-open',
      force: options?.propagate === true,
    })
  }

  function removeSession(port: number): void {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    disposeSessionTerminal(session)

    try {
      session.ws?.close()
    } catch {
      // best-effort
    }

    sessions.value.delete(port)
    lastAppliedRendererType.delete(port)
    historyRefreshWaiters.delete(port)
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

  function attach(
    port: number,
    container: HTMLElement,
    options?: { propagate?: boolean },
  ): Promise<void> {
    const session = sessions.value.get(port)
    if (!session) {
      return Promise.resolve()
    }

    session.fitPropagationEnabled = options?.propagate ?? true

    if (session.terminalDisposed) {
      initializeSessionTerminal(session)
      session.isRestoring = true
    }

    const element = session.terminal.element

    if (!element) {
      return openWhenRenderable(port, container, options)
    }

    if (element.parentElement !== container) {
      element.remove()
      container.appendChild(element)
    }

    setupBrowserEventHandlers(session)
    scheduleFit(port, {
      immediate: true,
      reason: 'attach',
      force: options?.propagate === true,
    })

    return Promise.resolve()
  }

  function setupBrowserEventHandlers(session: Session): void {
    const element = session.terminal.element
    if (!element) return

    const typedElement = element as HTMLElement & {
      _silcBrowserEventTarget?: EventTarget | null
      _silcDocumentContextMenuHandler?: (e: MouseEvent) => void
      _silcDocumentMouseDownHandler?: (e: MouseEvent) => void
      _silcContextMenuHandler?: (e: MouseEvent) => void
      _silcMouseDownHandler?: (e: MouseEvent) => void
      _silcPasteEventHandler?: (e: Event) => void
    }

    const shadowRoot = element.shadowRoot
    const helperTextarea = shadowRoot?.querySelector('.xterm-helper-textarea') as HTMLTextAreaElement | null ?? null
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

    cleanupBrowserEventHandlers(session)

    const browserEventTarget = shadowRoot ?? helperTextarea ?? element
    typedElement._silcBrowserEventTarget = browserEventTarget

    const isTerminalTarget = (event: Event): boolean => {
      const path = typeof event.composedPath === 'function' ? event.composedPath() : []
      return path.includes(element) || path.includes(browserEventTarget) || (helperTextarea !== null && path.includes(helperTextarea))
    }

    const documentContextMenuHandler = (e: MouseEvent) => {
      if (!isTerminalTarget(e)) {
        return
      }

      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
      void pasteClipboardText(session.port)
    }
    element.ownerDocument.addEventListener('contextmenu', documentContextMenuHandler, true)
    typedElement._silcDocumentContextMenuHandler = documentContextMenuHandler

    const documentMouseDownHandler = (e: MouseEvent) => {
      if (e.button !== 2 || !isTerminalTarget(e)) {
        return
      }

      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
    }
    element.ownerDocument.addEventListener('mousedown', documentMouseDownHandler, true)
    typedElement._silcDocumentMouseDownHandler = documentMouseDownHandler

    const contextMenuHandler = (e: MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
      void pasteClipboardText(session.port)
    }
    browserEventTarget.addEventListener('contextmenu', contextMenuHandler as EventListener, true)
    typedElement._silcContextMenuHandler = contextMenuHandler

    const mouseDownHandler = (e: MouseEvent) => {
      if (e.button !== 2) {
        return
      }

      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
    }
    browserEventTarget.addEventListener('mousedown', mouseDownHandler as EventListener, true)
    typedElement._silcMouseDownHandler = mouseDownHandler

    const pasteEventHandler = (e: Event) => {
      e.preventDefault()
      e.stopImmediatePropagation()
      e.stopPropagation()
    }
    browserEventTarget.addEventListener('paste', pasteEventHandler as EventListener, true)
    typedElement._silcPasteEventHandler = pasteEventHandler
  }

  async function applyMeasuredFit(
    port: number,
    options?: { propagate?: boolean; reason?: string; force?: boolean },
  ): Promise<void> {
    const session = sessions.value.get(port)
    const terminalElement = session?.terminal.element
    const container = terminalElement?.parentElement

    if (!session || !terminalElement || !container || !isElementRenderable(container)) {
      return
    }

    const geometry = proposeTerminalGeometry(session.terminal, session.fitAddon, container, {
      maxCols: MAX_COLS,
      maxRows: MAX_ROWS,
    })
    if (!geometry) {
      return
    }

    const previousGeometry = getPreviousGeometry(session)
    const rowsChanged = session.lastSize?.rows !== geometry.rows
    const colsChanged = session.lastSize?.cols !== geometry.cols
    const payloadChanged = rowsChanged || colsChanged
    const shouldResizeTerminal = options?.force === true || payloadChanged
    const measuredChanged = hasGeometryChanged(previousGeometry, geometry)
    const previousRenderer = lastAppliedRendererType.get(port)

    if (shouldResizeTerminal) {
      session.terminal.resize(geometry.cols, geometry.rows)
    }

    session.lastSize = { rows: geometry.rows, cols: geometry.cols }
    session.lastMeasuredSize = {
      width: geometry.width,
      height: geometry.height,
      dpr: geometry.dpr,
    }

    const shouldPropagate = options?.propagate ?? session.fitPropagationEnabled

    if (shouldPropagate && shouldResizeTerminal) {
      try {
        await resizeSession(port, geometry.rows, geometry.cols)
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        if (message.includes('HTTP 410')) {
          setStatus(port, 'dead')
          return
        }
        console.error(
          `[TerminalManager] applyMeasuredFit error for port ${port} (${options?.reason ?? 'unknown'}):`,
          err,
        )
      }
    }

    if (previousRenderer !== session.rendererType || measuredChanged) {
      refreshRendererAfterSwap(session)
    }

    lastAppliedRendererType.set(port, session.rendererType)
  }

  function scheduleFit(
    port: number,
    options?: { propagate?: boolean; immediate?: boolean; reason?: string; force?: boolean },
  ): void {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    clearPendingLayoutWork(session)

    const runFit = () => {
      void applyMeasuredFit(port, {
        propagate: options?.propagate,
        reason: options?.reason,
        force: options?.force,
      })
    }

    if (options?.immediate === true) {
      session.pendingAnimationFrame = requestAnimationFrame(() => {
        session.pendingAnimationFrame = null
        runFit()
      })
      return
    }

    session.pendingFitTimer = setTimeout(() => {
      session.pendingFitTimer = null
      session.pendingAnimationFrame = requestAnimationFrame(() => {
        session.pendingAnimationFrame = null
        runFit()
      })
    }, FIT_DEBOUNCE_MS)
  }

  function detach(port: number): void {
    const session = sessions.value.get(port)
    if (!session || session.terminalDisposed) {
      return
    }

    disposeSessionTerminal(session)
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
    const orderedSessions = new Map<number, Session>()

    for (const daemonSession of daemonSessions) {
      const session = upsertDaemonSession(daemonSession)
      orderedSessions.set(daemonSession.port, session)
    }

    for (const port of Array.from(sessions.value.keys())) {
      if (!daemonPorts.has(port)) {
        removeSession(port)
      }
    }

    sessions.value = orderedSessions
  }

  function applySessionOrder(ports: number[]): void {
    const orderedSessions = new Map<number, Session>()

    for (const port of ports) {
      const session = sessions.value.get(port)
      if (session) {
        orderedSessions.set(port, session)
      }
    }

    if (orderedSessions.size !== sessions.value.size) {
      return
    }

    sessions.value = orderedSessions
  }

  function applyTheme(theme: ResolvedTheme): void {
    currentTheme.value = theme
    const terminalTheme = getTerminalTheme(theme)

    for (const session of sessions.value.values()) {
      if (session.terminalDisposed) {
        continue
      }

      session.terminal.options.theme = terminalTheme
      refreshRendererAfterSwap(session)
    }
  }

  function safeWrite(port: number, data: Uint8Array): void {
    const session = sessions.value.get(port)
    if (!session) return

    if (session.terminalDisposed) {
      return
    }

    if (data.byteLength === 0) {
      return
    }

    session.writeQueue.push(data)

    if (!session.writePending && !session.writeInFlight) {
      processWriteQueue(port)
    }
  }

  function processWriteQueue(port: number): void {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    if (session.writeQueue.length === 0) {
      session.writePending = false
      session.writeInFlight = false
      resolveFlushWaiters(session)
      return
    }

    session.writePending = true
    session.writeInFlight = true
    const chunk = session.writeQueue.shift()

    if (!chunk) {
      session.writePending = false
      session.writeInFlight = false
      resolveFlushWaiters(session)
      return
    }

    session.terminal.write(chunk, () => {
      session.writeInFlight = false

      if (session.writeQueue.length > 0) {
        processWriteQueue(port)
      } else {
        session.writePending = false
        resolveFlushWaiters(session)
      }
    })
  }

  async function flushWrites(port: number): Promise<void> {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    if (!session.writePending && !session.writeInFlight && session.writeQueue.length === 0) {
      return
    }

    await new Promise<void>((resolve) => {
      session.flushWaiters.push(resolve)
      resolveFlushWaiters(session)
    })
  }

  function waitForHistoryRefresh(port: number): Promise<void> {
    return new Promise((resolve) => {
      const waiters = historyRefreshWaiters.get(port) ?? []
      waiters.push(resolve)
      historyRefreshWaiters.set(port, waiters)
    })
  }

  function resolveHistoryRefresh(port: number): void {
    const session = sessions.value.get(port)
    if (session) {
      session.isRestoring = false
    }

    const waiters = historyRefreshWaiters.get(port)
    if (!waiters) {
      return
    }

    historyRefreshWaiters.delete(port)
    for (const resolve of waiters) {
      resolve()
    }
  }

  function cancelHistoryRefresh(port: number): void {
    const session = sessions.value.get(port)
    if (session) {
      session.isRestoring = false
    }

    const waiters = historyRefreshWaiters.get(port)
    if (!waiters) {
      return
    }

    historyRefreshWaiters.delete(port)
    for (const resolve of waiters) {
      resolve()
    }
  }

  function forceRedraw(port: number): void {
    const session = sessions.value.get(port)
    if (!session) {
      return
    }

    forceTerminalRedraw(session)
  }

  function refreshTerminalSurface(port: number): void {
    scheduleFit(port, { immediate: true, reason: 'refresh-terminal-surface' })
  }

  function getPreviousGeometry(session: Session): TerminalGeometry | null {
    if (!session.lastSize || !session.lastMeasuredSize) {
      return null
    }

    return {
      cols: session.lastSize.cols,
      rows: session.lastSize.rows,
      width: session.lastMeasuredSize.width,
      height: session.lastMeasuredSize.height,
      dpr: session.lastMeasuredSize.dpr,
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
    applyMeasuredFit,
    scheduleFit,
    flushWrites,
    waitForHistoryRefresh,
    resolveHistoryRefresh,
    cancelHistoryRefresh,
    forceRedraw,
    refreshTerminalSurface,
    pasteClipboardText,
    setStatus,
    setDisconnectReason,
    setWs,
    reconcileSessions,
    upsertDaemonSession,
    updateSessionTitle,
    updateSessionCwd,
    applySessionOrder,
    safeWrite,
    applyTheme,
  }
})
