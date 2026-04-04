import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Sidebar from '../components/Sidebar.vue'

vi.mock('@/lib/daemonApi', () => ({
  listSessions: vi.fn().mockResolvedValue([]),
  createSession: vi.fn(),
  getDefaults: vi.fn().mockResolvedValue({
    cwd: '',
    shell: 'bash',
    share_mode: false,
    manager_url: '',
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
})
