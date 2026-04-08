// FILE: manager_web_ui/src/__tests__/ManagerSettingsModal.spec.ts
// PURPOSE: Verify the manager settings modal save-state indicator and staged draft behavior.
// OWNS: Modal save feedback and form emission coverage.
// DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md

import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ManagerSettingsModal from '@/components/ManagerSettingsModal.vue'

describe('ManagerSettingsModal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('shows the save-state indicator and error copy', async () => {
    const wrapper = mount(ManagerSettingsModal, {
      props: {
        open: true,
        managerThemePreset: 'github',
        terminalThemePreset: 'amoled',
        fontSize: 16,
        lineHeight: 1.2,
        saveState: 'idle',
      },
      global: {
        stubs: {
          Teleport: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Ready')
    expect(wrapper.get('[data-save-status-dot]').text()).toBe('')

    await wrapper.setProps({ saveState: 'saving' })
    expect(wrapper.text()).toContain('Saving')
    expect(wrapper.text()).toContain('Saving...')

    await wrapper.setProps({ saveState: 'success' })
    expect(wrapper.text()).toContain('Saved')

    await wrapper.setProps({ saveState: 'failure', saveError: 'daemon offline' })
    expect(wrapper.text()).toContain('daemon offline')
  })

  it('emits the staged settings on save', async () => {
    const wrapper = mount(ManagerSettingsModal, {
      props: {
        open: true,
        managerThemePreset: 'github',
        terminalThemePreset: 'amoled',
        fontSize: 16,
        lineHeight: 1.2,
      },
      global: {
        stubs: {
          Teleport: true,
        },
      },
    })

    await wrapper.find('select').setValue('nord')
    expect(wrapper.emitted('preview')?.[0]?.[0]).toEqual({ managerThemePreset: 'nord' })
    await wrapper.findAll('select')[1].setValue('gruvbox')
    expect(wrapper.emitted('preview')?.[1]?.[0]).toEqual({ terminalThemePreset: 'gruvbox' })
    await wrapper.find('input[type="number"]').setValue(19)
    await wrapper.findAll('input[type="number"]')[1].setValue(1.25)
    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({
      managerThemePreset: 'nord',
      terminalThemePreset: 'gruvbox',
      fontSize: 19,
      lineHeight: 1.25,
    })
  })
})
