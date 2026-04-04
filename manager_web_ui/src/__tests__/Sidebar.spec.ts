import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Sidebar from '../components/Sidebar.vue'

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
}))

vi.mock('qrcode', () => ({
  default: {
    toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,stub'),
  },
}))

describe('Sidebar', () => {
  beforeEach(() => {
    localStorage.clear()
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
})
