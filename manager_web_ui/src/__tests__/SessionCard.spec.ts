// FILE: manager_web_ui/src/__tests__/SessionCard.spec.ts
// PURPOSE: Verify dormant home cards render a sleeping state without losing navigation.
// OWNS: Session card dormant-state rendering coverage.

import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionCard from '../components/SessionCard.vue'

const mockClipboardWriteText = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))

vi.mock('@/stores/terminalManager', () => ({
    useTerminalManager: () => ({
      getSession: () => ({
        port: 22001,
        name: 'sleepy',
        title: 'Bash',
        shell: 'bash',
        cwd: '/work/sleepy',
        command: { text: 'npm run dev', source: 'shell', start_ts: '2026-04-09T00:00:00Z' },
        status: 'dormant',
      }),
    }),
}))

describe('SessionCard', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: mockClipboardWriteText },
    })
    mockClipboardWriteText.mockClear()
  })

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
    expect(wrapper.text()).toContain('npm run dev')
    expect(wrapper.find('.session-card').classes()).toContain('grayscale')
  })

  it('copies the command without triggering card navigation', async () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }, { path: '/:port', component: { template: '<div />' } }],
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

    const command = wrapper.findAll('[role="button"]').find((node) => node.text() === 'npm run dev')
    expect(command).toBeTruthy()
    await command?.trigger('click')

    expect(mockClipboardWriteText).toHaveBeenCalledWith('npm run dev')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
