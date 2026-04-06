// FILE: manager_web_ui/src/__tests__/Sidebar.spec.ts
// PURPOSE: Verify sidebar session creation hints, rename prompt flow, and drag reorder wiring.
// OWNS: Sidebar component interaction coverage for rename and reorder actions.
// DOCS: agent_chat/plan_manager_qol_2026-04-05.md

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import packageJson from '../../package.json'
import Sidebar from '../components/Sidebar.vue'
import SidebarSessionRow from '../components/SidebarSessionRow.vue'

type MockSession = {
  port: number
  name: string
  title: string
  shell: string
  cwd: string
  status: string
}

const mockTerminalManager = {
  sessionList: [] as MockSession[],
  focusedPort: null as number | null,
  reconcileSessions: vi.fn(),
  upsertDaemonSession: vi.fn(),
  removeSession: vi.fn(),
  applySessionOrder: vi.fn(),
}

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => mockTerminalManager,
}))

vi.mock('@/lib/daemonApi', () => ({
  listSessions: vi.fn().mockResolvedValue([]),
  createSession: vi.fn(),
  getDefaults: vi.fn().mockResolvedValue({
    cwd: '',
    shell: 'bash',
    share_mode: false,
    manager_url: '',
    shell_options: [
      { type: 'pwsh', label: 'PowerShell', path: 'C:/Program Files/PowerShell/7/pwsh.exe' },
      { type: 'bash', label: 'Bash', path: '/usr/bin/bash' },
    ],
  }),
  renameSession: vi.fn(),
  reorderSessions: vi.fn(),
}))

vi.mock('@dnd-kit/vue', () => ({
  DragDropProvider: {
    name: 'DragDropProvider',
    emits: ['dragEnd'],
    template: '<div><slot /></div>',
  },
  useDraggable: () => ({
    isDragging: ref(false),
  }),
  useDroppable: () => ({
    isDropTarget: ref(false),
  }),
}))

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,stub'),
  },
}))

describe('Sidebar', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
    localStorage.clear()
    mockTerminalManager.sessionList = [
      {
        port: 1101,
        name: 'alpha',
        title: 'Bash',
        shell: 'bash',
        cwd: '/work/alpha',
        status: 'active',
      },
      {
        port: 1102,
        name: 'beta',
        title: 'Shell',
        shell: 'bash',
        cwd: '/work/beta',
        status: 'dormant',
      },
      {
        port: 1103,
        name: 'gamma',
        title: 'Shell',
        shell: 'bash',
        cwd: '/work/gamma',
        status: 'idle',
      },
    ]
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
  })

  it('renders a collapsed icon rail', async () => {
    localStorage.setItem('silc.sidebarCollapsed', 'true')

    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    expect(wrapper.find('[title="Expand sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[title="Create new session"]').exists()).toBe(true)
  })

  it('restores the sidebar width from localStorage', async () => {
    localStorage.setItem('silc.sidebarWidth', '300')

    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    expect(wrapper.find('aside').attributes('style')).toContain('width: 300px')
  })

  it('persists a resized sidebar width', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    const handle = wrapper.get('[data-testid="sidebar-resize-handle"]')
    await handle.trigger('mousedown', { clientX: 312 })
    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 318 }))
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))

    expect(localStorage.getItem('silc.sidebarWidth')).toBe('318')
  })

  it('shows a local mode hint when sharing is off', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Local mode')
    expect(wrapper.text()).toContain('Restart the daemon in shared mode')
    expect(wrapper.text()).toContain(`Built v${packageJson.version}`)
  })

  it('lists shell choices in the new session modal', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()
    await wrapper.find('[title="Create new session"]').trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('PowerShell')
    expect(document.body.textContent).toContain('Bash')
    expect(document.body.textContent).toContain('Default')
  })

  it('renders dormant sessions without a status label', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()

    expect(wrapper.text()).not.toContain('sleeping')
  })

  it('prompts to rename a session on double click', async () => {
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('delta')
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined)
    const { renameSession } = await import('@/lib/daemonApi')
    const renameSessionMock = vi.mocked(renameSession)
    renameSessionMock.mockResolvedValue({
      port: 1101,
      name: 'delta',
      title: 'Bash',
      session_id: 'sess-1',
      shell: 'bash',
      cwd: '/work/alpha',
      title_updated_at: null,
      idle_seconds: 0,
      alive: true,
      runtime_state: 'running',
      dormant: false,
    })

    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()
    await wrapper.findComponent(SidebarSessionRow).trigger('dblclick')
    await flushPromises()

    expect(promptSpy).toHaveBeenCalledWith('Rename session', 'alpha')
    expect(renameSessionMock).toHaveBeenCalledWith(1101, 'delta')
    expect(mockTerminalManager.upsertDaemonSession).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'delta' }),
    )
    expect(alertSpy).not.toHaveBeenCalled()
  })

  it('blocks duplicate names before renaming', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('beta')
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined)
    const { renameSession } = await import('@/lib/daemonApi')
    const renameSessionMock = vi.mocked(renameSession)

    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()
    await wrapper.findComponent(SidebarSessionRow).trigger('dblclick')
    await flushPromises()

    expect(renameSessionMock).not.toHaveBeenCalled()
    expect(alertSpy).toHaveBeenCalledWith("Session name 'beta' is already in use.")
  })

  it('reorders sessions through the drag end flow', async () => {
    const { reorderSessions } = await import('@/lib/daemonApi')
    const reorderSessionsMock = vi.mocked(reorderSessions)
    reorderSessionsMock.mockResolvedValue({
      sessions: [
        {
          port: 1103,
          name: 'gamma',
          title: 'Shell',
          session_id: 'sess-3',
          shell: 'bash',
          cwd: '/work/gamma',
          title_updated_at: null,
          idle_seconds: 0,
          alive: true,
          runtime_state: 'running',
          dormant: false,
        },
        {
          port: 1101,
          name: 'alpha',
          title: 'Bash',
          session_id: 'sess-1',
          shell: 'bash',
          cwd: '/work/alpha',
          title_updated_at: null,
          idle_seconds: 0,
          alive: true,
          runtime_state: 'running',
          dormant: false,
        },
        {
          port: 1102,
          name: 'beta',
          title: 'Shell',
          session_id: 'sess-2',
          shell: 'bash',
          cwd: '/work/beta',
          title_updated_at: null,
          idle_seconds: 0,
          alive: true,
          runtime_state: 'running',
          dormant: false,
        },
      ],
    })

    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(Sidebar, {
      global: {
        plugins: [createPinia(), router],
      },
    })

    await flushPromises()
    wrapper.findComponent({ name: 'DragDropProvider' }).vm.$emit('dragEnd', {
      canceled: false,
      operation: {
        source: { id: 1103 },
        target: { id: 1101 },
      },
    })
    await flushPromises()

    expect(mockTerminalManager.applySessionOrder).toHaveBeenCalledWith([1103, 1101, 1102])
    expect(reorderSessionsMock).toHaveBeenCalledWith([1103, 1101, 1102])
    expect(mockTerminalManager.reconcileSessions.mock.calls[0][0].map((session: { port: number }) => session.port)).toEqual([1103, 1101, 1102])
  })
})
