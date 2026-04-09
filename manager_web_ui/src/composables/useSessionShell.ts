// FILE: manager_web_ui/src/composables/useSessionShell.ts
// PURPOSE: Hold the shared session-shell lifecycle, recovery, and terminal command logic.
// OWNS: Session bootstrap, reconnect/wake flows, terminal actions, and session exit notifications.
// EXPORTS: useSessionShell - composable for single-session terminal behavior.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md, agent_chat/plan_session_end_splash_2026-04-09.md

import { computed, nextTick, onMounted, onUnmounted, ref, watch, type ComputedRef } from 'vue'
import { useTerminalManager } from '@/stores/terminalManager'
import { listSessions, closeSession, killSession, restartSession, unloadSession, sendInterrupt, sendSigkill, sendSigterm, clearSession } from '@/lib/daemonApi'
import { connectWebSocket, requestHistoryFrame, sendInputFrame } from '@/lib/websocket'

type OperationTone = 'info' | 'danger' | 'neutral'

interface ActiveOperation {
  label: string
  stage: string
  detail: string
  tone: OperationTone
}

type SessionShellSurface = 'manager' | 'standalone'

interface TerminalEndState {
  title: string
  detail: string
  cause: 'unload' | 'close' | 'kill' | 'disappear'
}

export function useSessionShell(
  port: ComputedRef<number>,
  surface: SessionShellSurface,
  onExit: () => void,
  onPortChange: (port: number) => void,
) {
  const manager = useTerminalManager()
  const reconnecting = ref(false)
  const activeOperation = ref<ActiveOperation | null>(null)
  const terminalEndState = ref<TerminalEndState | null>(null)
  const sessionBootstrapped = ref(false)

  const session = computed(() => manager.getSession(port.value))
  const isDormant = computed(() => session.value?.status === 'dormant')
  const isActive = computed(
    () => session.value?.status === 'active' && session.value?.ws?.readyState === WebSocket.OPEN,
  )
  const isRestarting = computed(() => session.value?.status === 'restarting')
  const hasConnectionProblem = computed(() => terminalEndState.value === null && !isActive.value && !isDormant.value)
  const controlsDisabled = computed(
    () => terminalEndState.value !== null || hasConnectionProblem.value || activeOperation.value !== null,
  )
  const disconnectReason = computed(() => session.value?.disconnectReason ?? '')

  function logSessionShell(message: string, extra?: Record<string, unknown>): void {
    console.info('[SessionShell]', message, {
      port: port.value,
      status: session.value?.status ?? null,
      bootstrapped: sessionBootstrapped.value,
      reconnecting: reconnecting.value,
      ...extra,
    })
  }

  function tip(primary: string, secondary: string): string {
    return `${primary}\n${secondary}`
  }

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms))
  }

  function clearTerminalEndState(): void {
    terminalEndState.value = null
  }

  function showStandaloneTerminalEndState(cause: TerminalEndState['cause']): void {
    terminalEndState.value = {
      title: 'Session ended',
      detail: 'This session is no longer interactive. You can now close this page or window.',
      cause,
    }
  }

  function handleTerminalEnd(cause: TerminalEndState['cause'], options?: { removeLocalSession?: boolean }): void {
    sessionBootstrapped.value = false

    if (options?.removeLocalSession) {
      manager.removeSession(port.value)
    }

    if (surface === 'standalone') {
      showStandaloneTerminalEndState(cause)
      return
    }

    onExit()
  }

  function closeWindow(): void {
    window.close()
  }

  async function ensureCurrentSessionVisible(): Promise<boolean> {
    try {
      logSessionShell('Fetching daemon session list to verify current session visibility')
      const daemonSessions = await listSessions()
      logSessionShell('Daemon session list fetched for visibility check', {
        count: daemonSessions.length,
        visible: daemonSessions.some((daemonSession) => daemonSession.port === port.value),
      })
      manager.reconcileSessions(daemonSessions)

      if (!daemonSessions.some((daemonSession) => daemonSession.port === port.value)) {
        logSessionShell('Current session disappeared from daemon list; ending shell view')
        handleTerminalEnd('disappear', { removeLocalSession: true })
        return false
      }

      logSessionShell('Current session remains visible in daemon list')
      return true
    } catch (err) {
      console.error('[SessionShell] Failed to sync session with daemon visibility check', err)
      return true
    }
  }

  async function waitForInteractiveSessionReady(
    targetPort: number,
    timeoutMs: number = 5000,
  ): Promise<boolean> {
    const start = Date.now()
    logSessionShell('Waiting for interactive session readiness', {
      targetPort,
      timeoutMs,
    })

    while (Date.now() - start < timeoutMs) {
      const currentSession = manager.getSession(targetPort)
      if (
        currentSession &&
        currentSession.status !== 'dormant' &&
        currentSession.terminal &&
        currentSession.ws?.readyState === WebSocket.OPEN
      ) {
        logSessionShell('Interactive session is ready', {
          targetPort,
          elapsedMs: Date.now() - start,
        })
        return true
      }

      await new Promise((resolve) => window.setTimeout(resolve, 100))
    }

    logSessionShell('Timeout waiting for interactive session readiness', {
      targetPort,
      timeoutMs,
    })
    return false
  }

  async function waitForSession(portToFind: number, timeoutMs: number = 5000): Promise<boolean> {
    const start = Date.now()
    logSessionShell('Waiting for daemon session to appear alive', {
      portToFind,
      timeoutMs,
    })

    while (Date.now() - start < timeoutMs) {
      const daemonSessions = await listSessions()
      logSessionShell('Polled daemon session list while waiting for live session', {
        portToFind,
        count: daemonSessions.length,
      })
      manager.reconcileSessions(daemonSessions)

      if (daemonSessions.some((daemonSession) => daemonSession.port === portToFind && daemonSession.alive)) {
        logSessionShell('Daemon reports target session alive', {
          portToFind,
          elapsedMs: Date.now() - start,
        })
        return true
      }

      await new Promise((resolve) => window.setTimeout(resolve, 250))
    }

    logSessionShell('Timeout waiting for daemon session to become alive', {
      portToFind,
      timeoutMs,
    })
    return false
  }

  async function ensureInteractiveSessionReady(): Promise<boolean> {
    if (!session.value || session.value.status !== 'dormant') {
      logSessionShell('Ensuring interactive readiness without wake path', {
        hasSession: Boolean(session.value),
      })
      return await waitForInteractiveSessionReady(port.value)
    }

    try {
      logSessionShell('Session is dormant; requesting wake via restart endpoint')
      await restartSession(port.value)
      const ready = await waitForSession(port.value)
      if (!ready) {
        logSessionShell('Early return: wake path timed out waiting for daemon session')
        return false
      }

      const visible = await ensureCurrentSessionVisible()
      if (!visible) {
        logSessionShell('Early return: wake path lost session visibility after restart')
        return false
      }

      logSessionShell('Wake path reached interactive readiness check')
      return await waitForInteractiveSessionReady(port.value)
    } catch (err) {
      console.error('[SessionShell] Failed to wake dormant session', err)
      return false
    }
  }

  async function runOperation(
    label: string,
    tone: OperationTone,
    steps: Array<{ stage: string; detail: string; run?: () => Promise<void> | void }>,
    minVisibleMs: number = 240,
  ): Promise<void> {
    const startedAt = performance.now()
    logSessionShell('Starting user operation', {
      label,
      tone,
      stepCount: steps.length,
    })
    activeOperation.value = {
      label,
      stage: steps[0]?.stage ?? 'Working',
      detail: steps[0]?.detail ?? '',
      tone,
    }

    await nextTick()

    try {
      for (const step of steps) {
        logSessionShell('Running operation step', {
          label,
          stage: step.stage,
        })
        activeOperation.value = {
          label,
          stage: step.stage,
          detail: step.detail,
          tone,
        }
        await nextTick()

        if (step.run) {
          await step.run()
        }
      }

      logSessionShell('User operation completed', {
        label,
        elapsedMs: Math.round(performance.now() - startedAt),
      })
      activeOperation.value = {
        label,
        stage: 'Complete',
        detail: 'The daemon and terminal have finished the requested work.',
        tone,
      }
      await nextTick()

      const elapsed = performance.now() - startedAt
      if (elapsed < minVisibleMs) {
        await sleep(minVisibleMs - elapsed)
      }
    } catch (err) {
      console.error('[SessionShell] User operation failed', {
        label,
        error: err,
      })
      activeOperation.value = {
        label,
        stage: 'Failed',
        detail: err instanceof Error ? err.message : String(err),
        tone: 'danger',
      }
      await nextTick()
      await sleep(1200)
      throw err
    } finally {
      if (activeOperation.value?.label === label) {
        activeOperation.value = null
      }
    }
  }

  async function refreshTerminal(): Promise<void> {
    if (isDormant.value) {
      logSessionShell('Early return: refresh skipped because session is dormant')
      return
    }

    const current = manager.getSession(port.value)
    if (current?.ws && current.ws.readyState === WebSocket.OPEN && current.terminal) {
      logSessionShell('Refreshing terminal from websocket history', {
        readyState: current.ws.readyState,
      })
      await manager.flushWrites(port.value)
      current.terminal.reset()
      const historyLoaded = manager.waitForHistoryRefresh(port.value)
      logSessionShell('Requesting history frame during terminal refresh')
      requestHistoryFrame(current.ws)
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          logSessionShell('History refresh timed out; forcing waiter resolution', {
            timeoutMs: 5000,
          })
          manager.resolveHistoryRefresh(port.value)
          reject(new Error('Timed out waiting for refreshed terminal history'))
        }, 5000)

        historyLoaded.then(
          () => {
            window.clearTimeout(timeout)
            logSessionShell('History refresh promise resolved successfully')
            resolve()
          },
          (err) => {
            window.clearTimeout(timeout)
            logSessionShell('History refresh promise rejected', {
              error: err instanceof Error ? err.message : String(err),
            })
            reject(err)
          },
        )
      })
      return
    }

    logSessionShell('Early return: refresh skipped because websocket or terminal is unavailable', {
      hasSession: Boolean(current),
      hasWs: Boolean(current?.ws),
      wsReadyState: current?.ws?.readyState ?? null,
      hasTerminal: Boolean(current?.terminal),
    })
  }

  async function reconnectSession(targetPort: number, waitForFreshSession: boolean = false): Promise<void> {
    if (reconnecting.value) {
      logSessionShell('Early return: reconnect skipped because reconnect is already in progress', {
        targetPort,
      })
      return
    }

    reconnecting.value = true
    logSessionShell('Starting reconnect flow', {
      targetPort,
      waitForFreshSession,
    })

    try {
      if (waitForFreshSession) {
        const ready = await waitForSession(targetPort)
        if (!ready) {
          logSessionShell('Reconnect failed waiting for fresh session to appear', {
            targetPort,
          })
          throw new Error(`Timed out waiting for session :${targetPort}`)
        }
      } else {
        logSessionShell('Reconnect fetching daemon sessions before reconnect attempt')
        const daemonSessions = await listSessions()
        manager.reconcileSessions(daemonSessions)
      }

      const nextSession = manager.getSession(targetPort)
      if (!nextSession || !nextSession.terminal) {
        logSessionShell('Reconnect aborted because local session or terminal is unavailable', {
          targetPort,
          hasSession: Boolean(nextSession),
          hasTerminal: Boolean(nextSession?.terminal),
        })
        throw new Error(`Session :${targetPort} is not available`)
      }

      await manager.flushWrites(targetPort)
      nextSession.terminal.reset()
      await manager.applyMeasuredFit(targetPort, {
        propagate: true,
        force: true,
        reason: 'reconnect-preconnect',
      })
      logSessionShell('Opening websocket as part of reconnect flow', {
        targetPort,
      })
      connectWebSocket(targetPort, { force: true })
      manager.refreshTerminalSurface(targetPort)
    } finally {
      reconnecting.value = false
      logSessionShell('Reconnect flow finished', {
        targetPort,
      })
    }
  }

  function sendViaWs(text: string): void {
    const current = manager.getSession(port.value)
    if (current?.ws && current.ws.readyState === WebSocket.OPEN) {
      logSessionShell('Sending websocket input from session shell', {
        bytes: text.length,
      })
      sendInputFrame(current.ws, text)
      return
    }

    logSessionShell('Dropped websocket input because socket is unavailable', {
      hasWs: Boolean(current?.ws),
      readyState: current?.ws?.readyState ?? null,
    })
  }

  async function handleRefresh(): Promise<void> {
    try {
      if (!(await ensureInteractiveSessionReady())) {
        return
      }

      const isVisible = await ensureCurrentSessionVisible()
      if (!isVisible) {
        return
      }

      await runOperation('Refresh', 'info', [
        {
          stage: 'Requesting backend history',
          detail: 'The daemon buffer is being asked for the current screen state.',
          run: async () => {
            await refreshTerminal()
          },
        },
        {
          stage: 'Refitting viewport',
          detail: 'The terminal viewport is recalculated to match the current browser size.',
          run: async () => {
            manager.refreshTerminalSurface(port.value)
            await nextTick()
          },
        },
        {
          stage: 'Repainting display',
          detail: 'The terminal surface is redrawn after the history and fit settle.',
          run: async () => {
            manager.forceRedraw(port.value)
            await nextTick()
          },
        },
        {
          stage: 'History restored',
          detail: 'The browser terminal now matches the daemon buffer again.',
          run: async () => {
            await nextTick()
          },
        },
      ])
    } catch (err) {
      console.error('Refresh failed:', err)
    }
  }

  async function handleClose(): Promise<void> {
    const currentPort = port.value

    try {
      await runOperation('Close session', 'neutral', [
        {
          stage: 'Requesting daemon close',
          detail: 'Asking the daemon to stop the session cleanly.',
          run: async () => {
            await closeSession(currentPort)
          },
        },
        {
          stage: 'Updating the UI',
          detail:
            surface === 'standalone'
              ? 'Ending the standalone session page in place.'
              : 'Removing the session locally and returning home.',
          run: async () => {
            handleTerminalEnd('close', { removeLocalSession: true })
          },
        },
      ])
    } catch (err) {
      console.error('Failed to close session:', err)
    }
  }

  async function handleUnload(): Promise<void> {
    const currentPort = port.value

    try {
      await runOperation('Unload session', 'neutral', [
        {
          stage: 'Requesting daemon unload',
          detail:
            'Asking the daemon to release the live runtime while preserving the session record.',
          run: async () => {
            await unloadSession(currentPort)
          },
        },
        {
          stage: 'Refreshing manager state',
          detail:
            surface === 'standalone'
              ? 'Ending the standalone page after the live shell is released.'
              : 'Reconciling the session list so the unloaded shell returns to its dormant state.',
          run: async () => {
            const daemonSessions = await listSessions()
            manager.reconcileSessions(daemonSessions)
            handleTerminalEnd('unload')
          },
        },
      ])
    } catch (err) {
      console.error('Failed to unload session:', err)
    }
  }

  async function handleKill(): Promise<void> {
    const currentPort = port.value

    try {
      await runOperation('Kill session', 'danger', [
        {
          stage: 'Requesting daemon kill',
          detail: 'Sending the hard-stop request to the daemon and PTY layer.',
          run: async () => {
            await killSession(currentPort)
          },
        },
        {
          stage: 'Updating the UI',
          detail:
            surface === 'standalone'
              ? 'Ending the standalone session page in place.'
              : 'Removing the dead session locally and returning home.',
          run: async () => {
            handleTerminalEnd('kill', { removeLocalSession: true })
          },
        },
      ])
    } catch (err) {
      console.error('Failed to kill session:', err)
    }
  }

  async function handleRestart(): Promise<void> {
    if (isRestarting.value) {
      logSessionShell('Early return: restart ignored because session is already restarting')
      return
    }

    try {
      await runOperation(
        'Restart session',
        'info',
        [
          {
            stage: 'Stopping the current shell',
            detail: 'The current PTY is being replaced with a fresh shell instance.',
            run: async () => {
              clearTerminalEndState()
              manager.setStatus(port.value, 'restarting')
              const result = await restartSession(port.value)
              logSessionShell('Daemon restart request completed', {
                requestedPort: port.value,
                resultPort: result.port,
              })
              await reconnectSession(result.port, true)

              if (result.port !== port.value) {
                logSessionShell('Restart returned a new port; notifying caller for redirect', {
                  previousPort: port.value,
                  nextPort: result.port,
                })
                onPortChange(result.port)
              }
            },
          },
          {
            stage: 'Reconnecting to the fresh session',
            detail: 'The browser terminal is waiting for the new websocket to come back.',
            run: async () => {
              await nextTick()
            },
          },
        ],
        420,
      )
    } catch (err) {
      manager.setStatus(port.value, 'dead')
      console.error('Failed to restart session:', err)
    }
  }

  async function handleReconnect(): Promise<void> {
    try {
      if (!(await ensureInteractiveSessionReady())) {
        return
      }

      await reconnectSession(port.value)
    } catch (err) {
      manager.setStatus(port.value, 'dead')
      console.error('Failed to reconnect session:', err)
    }
  }

  async function handleInterrupt(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation(
      'Send SIGINT',
      'info',
      [
        {
          stage: 'Sending interrupt',
          detail: 'The foreground process group is being asked to stop cleanly.',
          run: async () => {
            await sendInterrupt(port.value)
          },
        },
      ],
      160,
    )
  }

  async function handleSigterm(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation('Send SIGTERM', 'info', [
      {
        stage: 'Sending graceful termination',
        detail: 'The foreground process group is being asked to exit politely.',
        run: async () => {
          await sendSigterm(port.value)
        },
      },
    ])
  }

  async function handleSigkill(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation('Send SIGKILL', 'danger', [
      {
        stage: 'Sending force kill',
        detail: 'The foreground process group is being terminated immediately.',
        run: async () => {
          await sendSigkill(port.value)
        },
      },
    ])
  }

  async function handleClear(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation(
      'Clear terminal',
      'info',
      [
        {
          stage: 'Clearing session history',
          detail: 'The daemon is clearing the session output buffer.',
          run: async () => {
            await clearSession(port.value)
          },
        },
      ],
      160,
    )

    await refreshTerminal()
  }

  async function handlePaste(): Promise<void> {
    try {
      if (!(await ensureInteractiveSessionReady())) {
        return
      }

      await manager.pasteClipboardText(port.value)
    } catch (err) {
      console.error('Paste failed:', err)
    }
  }

  function scrollToBottom(): void {
    const current = manager.getSession(port.value)
    if (current?.terminal) {
      current.terminal.scrollToBottom()
    }
  }

  function handleBottom(): void {
    void (async () => {
      if (!(await ensureInteractiveSessionReady())) {
        return
      }

      scrollToBottom()
    })()
  }

  async function refitTerminal(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation(
      'Refit terminal',
      'info',
      [
        {
          stage: 'Measuring the viewport',
          detail: 'The terminal container is being remeasured and resized.',
          run: async () => {
            manager.refreshTerminalSurface(port.value)
            await nextTick()
          },
        },
      ],
      180,
    )
  }

  async function redrawTerminal(): Promise<void> {
    if (!(await ensureInteractiveSessionReady())) {
      return
    }

    await runOperation(
      'Redraw terminal',
      'info',
      [
        {
          stage: 'Repainting the renderer',
          detail: 'The xterm display is being repainted without changing the buffer.',
          run: async () => {
            manager.forceRedraw(port.value)
            await nextTick()
          },
        },
      ],
      180,
    )
  }

  function sendArrowKey(sequence: string): void {
    void (async () => {
      if (!(await ensureInteractiveSessionReady())) {
        return
      }

      sendViaWs(sequence)
    })()
  }

  async function bootstrapSession(): Promise<void> {
    try {
      logSessionShell('Starting session bootstrap flow')
      manager.setFocused(port.value)
      sessionBootstrapped.value = false
      clearTerminalEndState()

      const isVisible = await ensureCurrentSessionVisible()
      if (!isVisible) {
        logSessionShell('Early return: bootstrap stopped because session is not visible')
        return
      }

      if (session.value?.status === 'dormant') {
        logSessionShell('Bootstrap detected dormant session; requesting wake')
        await restartSession(port.value)
        const ready = await waitForSession(port.value)
        if (!ready) {
          logSessionShell('Early return: bootstrap wake path timed out waiting for session')
          return
        }
        const wakeVisible = await ensureCurrentSessionVisible()
        if (!wakeVisible) {
          logSessionShell('Early return: bootstrap wake path lost session visibility')
          return
        }
      }

      const interactiveReady = await waitForInteractiveSessionReady(port.value)
      if (!interactiveReady) {
        logSessionShell('Early return: bootstrap timed out waiting for interactive readiness')
        return
      }

      sessionBootstrapped.value = true
      clearTerminalEndState()
      logSessionShell('Session bootstrap marked complete; refreshing terminal history')
      await refreshTerminal()
    } catch (err) {
      console.error('[SessionShell] Failed to bootstrap session', err)
    }
  }

  watch(session, (next, previous) => {
    if (!sessionBootstrapped.value || previous === undefined || next !== undefined) {
      return
    }

    logSessionShell('Observed active session removal after bootstrap; ending shell view')
    handleTerminalEnd('disappear')
  })

  watch(port, () => {
    logSessionShell('Observed port change; re-running bootstrap flow')
    void bootstrapSession()
  })

  onMounted(() => {
    logSessionShell('Session shell mounted; bootstrapping current port')
    void bootstrapSession()
  })

  onUnmounted(() => {
    logSessionShell('Session shell unmounted; clearing focus and bootstrap flag')
    sessionBootstrapped.value = false
    manager.setFocused(null)
  })

  return {
    port,
    session,
    isDormant,
    isRestarting,
    reconnecting,
    activeOperation,
    terminalEndState,
    hasConnectionProblem,
    controlsDisabled,
    disconnectReason,
    connectionLabel: computed(() => {
      if (isDormant.value) {
        return 'This session is sleeping on disk until resurrected.'
      }

      if (disconnectReason.value === 'Session claimed by another client') {
        return 'This shell is now controlled from another client.'
      }

      switch (session.value?.status) {
        case 'connecting':
          return 'Connecting to shell websocket...'
        case 'restarting':
          return 'Restarting shell and waiting for PTY to come back...'
        case 'dead':
          return 'Shell websocket is down.'
        case 'idle':
          return 'Shell is disconnected.'
        default:
          return 'Shell is unavailable.'
      }
    }),
    tip,
    handleRefresh,
    handleClose,
    handleUnload,
    handleKill,
    handleRestart,
    handleReconnect,
    closeWindow,
    handleInterrupt,
    handleSigterm,
    handleSigkill,
    handleClear,
    handlePaste,
    handleBottom,
    refitTerminal,
    redrawTerminal,
    sendArrowKey,
  }
}
