<!-- FILE: manager_web_ui/src/components/ManagerSettingsModal.vue -->
<!-- PURPOSE: Present the manager appearance settings modal and stage edits before save. -->
<!-- OWNS: Settings dialog layout, local draft state, and save/cancel actions. -->
<!-- EXPORTS: ManagerSettingsModal - modal form for manager chrome and terminal presets. -->
<!-- DOCS: agent_chat/plan_web_manager_settings_polish_2026-04-08.md -->

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  THEME_PRESET_OPTIONS,
  type ThemePresetName,
} from '@/lib/themePresets'

type SaveState = 'idle' | 'saving' | 'success' | 'failure'

const props = defineProps<{
  open: boolean
  managerThemePreset: ThemePresetName
  terminalThemePreset: ThemePresetName
  fontSize: number
  lineHeight: number
  saveState?: SaveState
  saveError?: string
}>()

const emit = defineEmits<{
  close: []
  preview: [payload: {
    managerThemePreset?: ThemePresetName
    terminalThemePreset?: ThemePresetName
  }]
  save: [payload: {
    managerThemePreset: ThemePresetName
    terminalThemePreset: ThemePresetName
    fontSize: number
    lineHeight: number
  }]
}>()

const draftManagerThemePreset = ref<ThemePresetName>(props.managerThemePreset)
const draftTerminalThemePreset = ref<ThemePresetName>(props.terminalThemePreset)
const draftFontSize = ref(props.fontSize)
const draftLineHeight = ref(props.lineHeight)

const managerThemeLabel = computed(
  () => THEME_PRESET_OPTIONS.find(option => option.value === draftManagerThemePreset.value)?.label ?? draftManagerThemePreset.value,
)
const terminalThemeLabel = computed(
  () => THEME_PRESET_OPTIONS.find(option => option.value === draftTerminalThemePreset.value)?.label ?? draftTerminalThemePreset.value,
)

const currentSaveState = computed<SaveState>(() => props.saveState ?? 'idle')
const saveStatusText = computed(() => {
  if (currentSaveState.value === 'saving') return 'Saving'
  if (currentSaveState.value === 'success') return 'Saved'
  if (currentSaveState.value === 'failure') return props.saveError || 'Save failed'
  return 'Ready'
})

const saveStatusClasses = computed(() => {
  if (currentSaveState.value === 'saving') {
    return 'border-[var(--color-accent)] text-[var(--color-accent)]'
  }

  if (currentSaveState.value === 'success') {
    return 'border-[var(--color-success)] bg-[var(--color-success)] text-white'
  }

  if (currentSaveState.value === 'failure') {
    return 'border-[var(--color-error)] bg-[var(--color-error)] text-white'
  }

  return 'border-[var(--color-border-strong)] text-[var(--color-text-muted)]'
})

const saveButtonLabel = computed(() => {
  if (currentSaveState.value === 'saving') return 'Saving...'
  if (currentSaveState.value === 'success') return 'Saved'
  return 'Save'
})

function syncDraft(): void {
  draftManagerThemePreset.value = props.managerThemePreset
  draftTerminalThemePreset.value = props.terminalThemePreset
  draftFontSize.value = props.fontSize
  draftLineHeight.value = props.lineHeight
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      syncDraft()
    }
  },
  { immediate: true },
)

function handleSave(): void {
  emit('save', {
    managerThemePreset: draftManagerThemePreset.value,
    terminalThemePreset: draftTerminalThemePreset.value,
    fontSize: draftFontSize.value,
    lineHeight: draftLineHeight.value,
  })
}

function handleManagerThemeChange(): void {
  emit('preview', { managerThemePreset: draftManagerThemePreset.value })
}

function handleTerminalThemeChange(): void {
  emit('preview', { terminalThemePreset: draftTerminalThemePreset.value })
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-[var(--color-backdrop)] px-4 py-6"
      @click.self="emit('close')"
    >
      <div class="glass-panel w-full max-w-xl p-4 md:p-5">
        <div class="flex items-start justify-between gap-4 border-b border-[var(--color-border)] pb-3">
          <div>
            <p class="text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-muted)]">Settings</p>
            <h2 class="mt-1 font-[var(--font-display)] text-2xl text-[var(--color-text-primary)]">Manager appearance</h2>
            <p class="mt-1 text-sm text-[var(--color-text-secondary)]">
              Tune the outer shell separately from terminal colors.
            </p>
          </div>

          <button
            type="button"
            class="bar-button icon-button border border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
            title="Close settings"
            aria-label="Close settings"
            :disabled="currentSaveState === 'saving'"
            @click="emit('close')"
          >
            ×
          </button>
        </div>

        <form class="mt-4 grid gap-4" @submit.prevent="handleSave">
          <label class="grid gap-2">
            <span class="text-sm text-[var(--color-text-secondary)]">Manager theme preset</span>
            <select
              v-model="draftManagerThemePreset"
              @change="handleManagerThemeChange"
              :disabled="currentSaveState === 'saving'"
              class="w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
            >
              <option v-for="option in THEME_PRESET_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }} — {{ option.description }}
              </option>
            </select>
            <span class="text-xs text-[var(--color-text-muted)]">Current selection: {{ managerThemeLabel }}</span>
          </label>

          <label class="grid gap-2">
            <span class="text-sm text-[var(--color-text-secondary)]">Terminal theme preset</span>
            <select
              v-model="draftTerminalThemePreset"
              @change="handleTerminalThemeChange"
              :disabled="currentSaveState === 'saving'"
              class="w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
            >
              <option v-for="option in THEME_PRESET_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }} — {{ option.description }}
              </option>
            </select>
            <span class="text-xs text-[var(--color-text-muted)]">Current selection: {{ terminalThemeLabel }}</span>
          </label>

          <div class="grid gap-4 md:grid-cols-2">
            <label class="grid gap-2">
              <span class="text-sm text-[var(--color-text-secondary)]">Font size</span>
              <input
                v-model.number="draftFontSize"
                type="number"
                min="10"
                max="24"
                step="1"
                :disabled="currentSaveState === 'saving'"
                class="w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
              />
            </label>

            <label class="grid gap-2">
              <span class="text-sm text-[var(--color-text-secondary)]">Line height</span>
              <input
                v-model.number="draftLineHeight"
                type="number"
                min="1"
                max="2"
                step="0.05"
                :disabled="currentSaveState === 'saving'"
                class="w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
              />
            </label>
          </div>

          <p class="text-xs leading-5 text-[var(--color-text-muted)]">
            Scrollback, size, cursor blink, and font family stay on daemon defaults for now.
          </p>

          <p
            class="min-h-5 text-xs leading-5 text-[var(--color-text-muted)]"
            :class="{ 'text-[var(--color-error)]': currentSaveState === 'failure', 'text-[var(--color-success)]': currentSaveState === 'success' }"
            aria-live="polite"
          >
            {{ saveStatusText }}
          </p>

          <div class="flex justify-end gap-2 border-t border-[var(--color-border)] pt-3">
            <button
              type="button"
              class="bar-button border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-4 py-2 text-sm"
              :disabled="currentSaveState === 'saving'"
              @click="emit('close')"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="bar-button bar-button-accent px-4 py-2 text-sm font-medium"
              :disabled="currentSaveState === 'saving'"
            >
              <span class="inline-flex items-center gap-2">
                <span
                  class="inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-full border-2 transition-colors"
                  :class="saveStatusClasses"
                  data-save-status-dot
                  aria-hidden="true"
                >
                  <span
                    v-if="currentSaveState === 'saving'"
                    class="h-1.5 w-1.5 animate-spin rounded-full border border-current border-t-transparent"
                  />
                </span>
                <span>{{ saveButtonLabel }}</span>
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>
