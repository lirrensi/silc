// FILE: manager_web_ui/src/__tests__/terminalManager.spec.ts
// PURPOSE: Verify detached sessions snapshot, dispose, and rebuild fresh terminal instances.
// OWNS: Terminal store lifecycle coverage for snapshot restore and recreation.

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
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

  return { MockTerminal, MockFitAddon }
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
  resizeSession: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/lib/terminalRenderer', () => ({
  disposeRenderer: vi.fn(),
  enableRenderer: vi.fn().mockResolvedValue(undefined),
  forceTerminalRedraw: vi.fn(),
  refreshRendererAfterSwap: vi.fn(),
}))

vi.mock('@/lib/themes', () => ({
  getTerminalTheme: vi.fn(() => ({ background: '#000' })),
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
    const originalTerminal = session.terminal
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

    manager.attach(20000, container, { propagate: true })

    await Promise.resolve()

    expect(originalTerminal.open).toHaveBeenCalledWith(container)

    manager.detach(20000)

    expect(session.terminalDisposed).toBe(true)
    expect(originalTerminal.dispose).toHaveBeenCalled()

    manager.attach(20000, container, { propagate: true })

    await Promise.resolve()
    await Promise.resolve()

    expect(mocks.MockTerminal.instances).toHaveLength(2)
    expect(session.terminal).not.toBe(originalTerminal)
    expect(session.terminalDisposed).toBe(false)
    expect(session.isRestoring).toBe(true)
    expect(session.terminal.write).not.toHaveBeenCalled()

    container.remove()
  })
})
