// FILE: manager_web_ui/src/__tests__/terminalRenderer.spec.ts
// PURPOSE: Verify WebGL renderer setup registers context-loss handling before activation.
// OWNS: Renderer fallback order coverage.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { enableRenderer } from '../lib/terminalRenderer'

const mocks = vi.hoisted(() => {
  class MockWebglAddon {
    dispose = vi.fn()
    onContextLoss = vi.fn()
  }

  const loadAddon = vi.fn((addon: MockWebglAddon) => {
    expect(addon.onContextLoss).toHaveBeenCalledTimes(1)
  })

  const terminal = {
    element: document.createElement('div'),
    loadAddon,
    rows: 24,
    refresh: vi.fn(),
  }

  const session = {
    terminal,
    webglAddon: null,
    rendererType: 'dom' as const,
    rendererFailed: false,
  }

  return { MockWebglAddon, loadAddon, session }
})

vi.mock('@xterm/addon-webgl', () => ({
  WebglAddon: mocks.MockWebglAddon,
}))

describe('enableRenderer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.session.webglAddon = null
    mocks.session.rendererType = 'dom'
    mocks.session.rendererFailed = false
  })

  it('registers context-loss fallback before loading WebGL', async () => {
    await enableRenderer(mocks.session as never)

    expect(mocks.loadAddon).toHaveBeenCalledTimes(1)
    expect(mocks.session.rendererType).toBe('webgl')
    expect(mocks.session.rendererFailed).toBe(false)
    expect(mocks.session.webglAddon).toBeTruthy()
  })
})
