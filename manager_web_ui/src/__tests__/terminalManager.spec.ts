// FILE: manager_web_ui/src/__tests__/terminalManager.spec.ts
// PURPOSE: Verify detached sessions snapshot, dispose, and rebuild fresh terminal instances.
// OWNS: Terminal store lifecycle coverage for snapshot restore and recreation.

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const resizeSession = vi.fn().mockResolvedValue(undefined)

  class MockTerminal {
    static instances: MockTerminal[] = []

    element: HTMLElement | null = null
    rows = 30
    cols = 120
    unicode = { activeVersion: '' }
    options = { theme: null as unknown }
    loadAddon = vi.fn()
    attachCustomKeyEventHandler = vi.fn()
    onData = vi.fn(() => ({ dispose: vi.fn() }))
    write = vi.fn((data: Uint8Array, callback?: () => void) => {
      callback?.()
    })
    resize = vi.fn()
    open = vi.fn((container: HTMLElement) => {
      const element = document.createElement('div')
      this.element = element
      container.appendChild(element)
    })
    dispose = vi.fn(() => {
      this.element?.remove()
      this.element = null
    })
    hasSelection = vi.fn(() => false)
    getSelection = vi.fn(() => '')
    clearSelection = vi.fn()
    reset = vi.fn()
    refresh = vi.fn()
    clearTextureAtlas = vi.fn()

    constructor() {
      MockTerminal.instances.push(this)
    }
  }

  class MockFitAddon {
    proposeDimensions = vi.fn(() => ({ cols: 80, rows: 24 }))
  }

  return { MockTerminal, MockFitAddon, resizeSession }
})

vi.mock('@xterm/xterm', () => ({
  Terminal: mocks.MockTerminal,
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: mocks.MockFitAddon,
}))

vi.mock('@xterm/addon-unicode11', () => ({
  Unicode11Addon: class {},
}))

vi.mock('@xterm/addon-webgl', () => ({
  WebglAddon: class {
    dispose = vi.fn()
    onContextLoss = vi.fn()
  },
}))

vi.mock('@/lib/daemonApi', () => ({
  resizeSession: mocks.resizeSession,
  getSettings: vi.fn().mockResolvedValue({ ui: { managerTheme: 'amoled' }, terminal: {} }),
  updateSettings: vi.fn(),
}))

vi.mock('@/lib/terminalRenderer', () => ({
  disposeRenderer: vi.fn(),
  enableRenderer: vi.fn().mockResolvedValue(undefined),
  forceTerminalRedraw: vi.fn(),
  refreshRendererAfterSwap: vi.fn(),
}))

vi.mock('@/lib/themes', () => ({
  DEFAULT_TERMINAL_DEFAULTS: {
    cols: 120,
    rows: 30,
    scrollback: 5000,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    fontSize: 15,
    lineHeight: 1.05,
    cursorBlink: true,
  },
}))

vi.mock('@/lib/themePresets', () => ({
  getTerminalThemePreset: vi.fn(() => ({ background: '#000' })),
}))

import { useTerminalManager } from '../stores/terminalManager'

describe('terminalManager', () => {
  beforeEach(() => {
    mocks.MockTerminal.instances = []
    setActivePinia(createPinia())
    vi.stubGlobal(
      'requestAnimationFrame',
      ((callback: FrameRequestCallback) => {
        callback(0)
        return 1
      }) as typeof requestAnimationFrame,
    )
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  it('disposes on detach and recreates a fresh terminal on reattach', async () => {
    const manager = useTerminalManager()
    const session = manager.createSession(20000, 'session-1', 'bash')
    const container = document.createElement('div')

    expect(session.terminal).toBeNull()

    Object.defineProperty(container, 'getBoundingClientRect', {
      value: () => ({
        width: 800,
        height: 600,
        top: 0,
        right: 800,
        bottom: 600,
        left: 0,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    })
    document.body.appendChild(container)

    await manager.attach(20000, container, { propagate: true })

    await Promise.resolve()

    const originalTerminal = session.terminal
    expect(originalTerminal).not.toBeNull()

    expect(originalTerminal?.open).toHaveBeenCalledWith(container)

    manager.detach(20000)

    expect(session.terminalDisposed).toBe(true)
    expect(originalTerminal?.dispose).toHaveBeenCalled()

    await manager.attach(20000, container, { propagate: true })

    await Promise.resolve()
    await Promise.resolve()

    expect(mocks.MockTerminal.instances).toHaveLength(2)
    expect(session.terminal).not.toBe(originalTerminal)
    expect(session.terminalDisposed).toBe(false)
    expect(session.isRestoring).toBe(true)
    expect(session.terminal?.write).not.toHaveBeenCalled()

    container.remove()
  })

  it('forces a backend resize when an interactive attach claims control', async () => {
    const manager = useTerminalManager()
    const session = manager.createSession(20000, 'session-1', 'bash')
    const container = document.createElement('div')

    Object.defineProperty(container, 'getBoundingClientRect', {
      value: () => ({
        width: 800,
        height: 600,
        top: 0,
        right: 800,
        bottom: 600,
        left: 0,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    })
    document.body.appendChild(container)

    session.lastSize = { rows: 24, cols: 80 }
    session.lastMeasuredSize = { width: 800, height: 600, dpr: 1 }

    await manager.attach(20000, container, { propagate: false })
    await manager.applyMeasuredFit(20000, { propagate: true, force: true, reason: 'test-force-resize' })

    expect(session.terminal?.resize).toHaveBeenCalledWith(80, 24)
    expect(mocks.resizeSession).toHaveBeenCalledWith(20000, 24, 80)

    container.remove()
  })

  it('does not allocate a terminal while reconciling a dormant daemon session', () => {
    const manager = useTerminalManager()

    manager.reconcileSessions([
      {
        port: 20001,
        name: 'sleepy',
        title: 'Bash',
        session_id: 'session-2',
        shell: 'bash',
        cwd: '/work/sleepy',
        title_updated_at: null,
        idle_seconds: 0,
        alive: false,
        runtime_state: 'dormant',
        dormant: true,
      },
    ])

    const session = manager.getSession(20001)
    expect(session?.status).toBe('dormant')
    expect(session?.terminal).toBeNull()
    expect(mocks.MockTerminal.instances).toHaveLength(0)
  })
})
