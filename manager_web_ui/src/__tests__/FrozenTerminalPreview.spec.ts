// FILE: manager_web_ui/src/__tests__/FrozenTerminalPreview.spec.ts
// PURPOSE: Verify frozen snapshot rendering, refresh cadence, and disposal for Home previews.
// OWNS: Visibility lifecycle and snapshot refresh coverage for the preview component.
// DOCS: agent_chat/plan_ws_binary_framing_2026-04-05.md

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import FrozenTerminalPreview from '../components/FrozenTerminalPreview.vue'

const mocks = vi.hoisted(() => {
  const terminalInstances: Array<{ open: ReturnType<typeof vi.fn>; reset: ReturnType<typeof vi.fn>; write: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn>; options: { theme?: unknown }; element: HTMLElement | null; loadAddon: ReturnType<typeof vi.fn>; unicode: { activeVersion: string } }> = []
  const fitInstances: Array<{ fit: ReturnType<typeof vi.fn> }> = []
  const intersectionObservers: Array<{ callback: IntersectionObserverCallback; observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }> = []

  class MockTerminal {
    element: HTMLElement | null = null
    options: { theme?: unknown }
    unicode = { activeVersion: '' }
    open = vi.fn((element: HTMLElement) => {
      this.element = element
    })
    reset = vi.fn()
    write = vi.fn((_data: string | Uint8Array) => undefined)
    dispose = vi.fn()
    loadAddon = vi.fn()

    constructor(options: { theme?: unknown }) {
      this.options = options
      terminalInstances.push(this)
    }
  }

  class MockFitAddon {
    fit = vi.fn()
    proposeDimensions = vi.fn(() => ({ cols: 80, rows: 24 }))

    constructor() {
      fitInstances.push(this)
    }
  }

  class MockUnicode11Addon {}

  class MockIntersectionObserver {
    callback: IntersectionObserverCallback
    observe = vi.fn()
    disconnect = vi.fn()

    constructor(callback: IntersectionObserverCallback) {
      this.callback = callback
      intersectionObservers.push(this)
    }
  }

  class MockResizeObserver {
    observe = vi.fn()
    disconnect = vi.fn()

    constructor() {}
  }

  return {
    terminalInstances,
    fitInstances,
    intersectionObservers,
    MockTerminal,
    MockFitAddon,
    MockUnicode11Addon,
    MockIntersectionObserver,
    MockResizeObserver,
  }
})

vi.mock('@xterm/xterm', () => ({
  Terminal: mocks.MockTerminal,
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: mocks.MockFitAddon,
}))

vi.mock('@xterm/addon-unicode11', () => ({
  Unicode11Addon: mocks.MockUnicode11Addon,
}))

vi.mock('../lib/homePreview', () => ({
  loadHomePreviewSnapshot: vi.fn(async () => new Uint8Array([27, 91, 51, 49, 109, 82, 69, 68, 27, 91, 48, 109])),
}))

describe('FrozenTerminalPreview', () => {
  beforeEach(() => {
    mocks.terminalInstances.length = 0
    mocks.fitInstances.length = 0
    mocks.intersectionObservers.length = 0
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: '',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    vi.useFakeTimers()
    vi.stubGlobal('IntersectionObserver', mocks.MockIntersectionObserver)
    vi.stubGlobal('ResizeObserver', mocks.MockResizeObserver)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('renders a frozen colored snapshot and disposes on hide', async () => {
    const root = document.createElement('div')
    document.body.appendChild(root)

    const wrapper = mount(FrozenTerminalPreview, {
      attachTo: root,
      global: {
        plugins: [createPinia()],
      },
      props: {
        port: 1234,
        observerRoot: root,
        refreshMs: 1000,
      },
    })

    await wrapper.vm.$nextTick()
    expect(mocks.intersectionObservers).toHaveLength(1)

    mocks.intersectionObservers[0].callback([
      { isIntersecting: true } as IntersectionObserverEntry,
    ] as IntersectionObserverEntry[], mocks.intersectionObservers[0] as unknown as IntersectionObserver)

    await vi.advanceTimersByTimeAsync(200)
    await Promise.resolve()
    await Promise.resolve()

    expect(mocks.terminalInstances).toHaveLength(1)
    expect(mocks.terminalInstances[0].reset).toHaveBeenCalled()
    expect(mocks.terminalInstances[0].write).toHaveBeenCalledWith(expect.any(Uint8Array))

    await vi.advanceTimersByTimeAsync(1140)
    await Promise.resolve()

    expect(mocks.terminalInstances[0].write.mock.calls.length).toBeGreaterThanOrEqual(2)

    mocks.intersectionObservers[0].callback(
      [{ isIntersecting: false } as IntersectionObserverEntry] as IntersectionObserverEntry[],
      mocks.intersectionObservers[0] as unknown as IntersectionObserver,
    )

    expect(mocks.terminalInstances[0].dispose).toHaveBeenCalled()

    wrapper.unmount()
    document.body.removeChild(root)
  })
})
