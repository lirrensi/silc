// FILE: manager_web_ui/src/__tests__/SessionCard.spec.ts
// PURPOSE: Verify dormant home cards render a sleeping state without losing navigation.
// OWNS: Session card dormant-state rendering coverage.

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionCard from '../components/SessionCard.vue'

vi.mock('@/stores/terminalManager', () => ({
  useTerminalManager: () => ({
    getSession: () => ({
      port: 22001,
      name: 'sleepy',
      title: 'Bash',
      shell: 'bash',
      cwd: '/work/sleepy',
      status: 'dormant',
    }),
  }),
}))

describe('SessionCard', () => {
  it('renders dormant cards without a status label', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })

    await router.push('/')
    await router.isReady()

    const wrapper = mount(SessionCard, {
      global: {
        plugins: [createPinia(), router],
      },
      props: {
        port: 22001,
      },
    })

    expect(wrapper.text()).not.toContain('sleeping')
    expect(wrapper.find('.session-card').classes()).toContain('grayscale')
  })
})
