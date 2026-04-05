// FILE: manager_web_ui/src/__tests__/App.spec.ts
// PURPOSE: Verify the app shell mounts cleanly with the sidebar and routed layout.
// OWNS: App shell smoke coverage and layout bootstrapping.
// DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md, agent_chat/plan_manager_qol_2026-04-05.md

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'

vi.mock('@dnd-kit/vue', () => ({
  DragDropProvider: {
    name: 'DragDropProvider',
    template: '<div><slot /></div>',
  },
  useDraggable: () => ({
    isDragging: { value: false },
  }),
  useDroppable: () => ({
    isDropTarget: { value: false },
  }),
}))

vi.mock('@/lib/daemonEvents', () => ({
  startDaemonEvents: vi.fn(),
  stopDaemonEvents: vi.fn(),
}))

describe('App', () => {
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

  it('mounts with the shell layout', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          Sidebar: true,
        },
      },
    })

    expect(wrapper.exists()).toBe(true)
  })
})
