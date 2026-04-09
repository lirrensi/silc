<!-- FILE: manager_web_ui/src/components/Sidebar.vue -->
<!-- PURPOSE: Render the manager sidebar, session creation controls, settings access, and session rename/reorder actions. -->
<!-- OWNS: Sidebar layout, session creation modal, settings modal trigger, live session list controls, and share/defaults UI. -->
<!-- EXPORTS: SidebarPanel - manager sidebar component. -->
<!-- DOCS: agent_chat/plan_daemon_manager_events_2026-04-05.md, agent_chat/plan_manager_qol_2026-04-05.md, agent_chat/plan_web_manager_settings_polish_2026-04-08.md -->

<script setup lang="ts">

defineOptions({ name: 'SidebarPanel' })

import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { DragDropProvider } from '@dnd-kit/vue'
import QRCode from 'qrcode'
import { useRoute, useRouter } from 'vue-router'
import packageJson from '../../package.json'
import SidebarSessionRow from '@/components/SidebarSessionRow.vue'
import ManagerSettingsModal from '@/components/ManagerSettingsModal.vue'
import {
  bulkClearSessions,
  bulkCloseSessions,
  bulkKillSessions,
  bulkRestartSessions,
  bulkSendSigintSessions,
  bulkSendSigkillSessions,
  bulkSendSigtermSessions,
  bulkUnloadSessions,
  createSession,
  getDefaults,
  listSessions,
  renameSession,
  reorderSessions,
} from '@/lib/daemonApi'
import { useTerminalManager } from '@/stores/terminalManager'
import { useUiStore } from '@/stores/ui'
import type { ThemePresetName } from '@/lib/themePresets'
import type { DaemonShellOption } from '@/lib/daemonApi'
import type { Session } from '@/types/session'

const router = useRouter()
const route = useRoute()
const manager = useTerminalManager()
const ui = useUiStore()

const sessions = computed(() => manager.sessionList)
const sidebarWidthStyle = computed(() => {
  if (ui.isMobileNavOpen) {
    return { width: 'min(24rem, 88vw)' }
  }

  return {
    width: ui.isSidebarCollapsed ? '3.75rem' : `${ui.sidebarWidth}px`,
  }
})

const isResizing = ref(false)

// New session modal state
const showNewSessionModal = ref(false)
const newSessionPath = ref('')
const defaultSessionPath = ref('')
const defaultShell = ref('shell')
const shellOptions = ref<DaemonShellOption[]>([])
const selectedShell = ref('')
const selectedShellLabel = computed(() => {
  return shellOptions.value.find(option => option.type === selectedShell.value)?.label ?? defaultShell.value
})
const shareMode = ref(false)
const shareUrl = ref('')
const shareQrCode = ref('')
const showShareDetails = ref(false)
const isCreatingSession = ref(false)
const createError = ref('')
const showSettingsModal = ref(false)
const showBulkCommandModal = ref(false)
const isRunningBulkCommand = ref(false)
const bulkCommandError = ref('')
const settingsSaveState = ref<'idle' | 'saving' | 'success' | 'failure'>('idle')
const settingsSaveError = ref('')
const settingsPreviewSnapshot = ref({
  managerThemePreset: ui.managerThemePreset,
  terminalThemePreset: ui.terminalThemePreset,
})
let settingsSaveCloseTimer: number | null = null
const builtVersion = `v${packageJson.version}`
const bulkCommandActions = [
  { label: 'Unload', run: bulkUnloadSessions },
  { label: 'Restart', run: bulkRestartSessions },
  { label: 'Close Session', run: bulkCloseSessions },
  { label: 'Close Forcefully', run: bulkKillSessions },
  { label: 'Clear', run: bulkClearSessions },
  { label: 'SIGINT', run: bulkSendSigintSessions },
  { label: 'SIGTERM', run: bulkSendSigtermSessions },
  { label: 'SIGKILL', run: bulkSendSigkillSessions },
] as const

function selectSession(port: number): void {
  router.push(`/${port}`)
  ui.closeMobileNav()
}

async function handleRenameSession(session: Session): Promise<void> {
  const currentName = session.name.trim()
  const nextName = window.prompt('Rename session', currentName)
  if (nextName === null) return

  const normalizedName = nextName.trim().toLowerCase()
  if (!normalizedName || normalizedName === currentName) {
    return
  }

  if (manager.sessionList.some(other => other.port !== session.port && other.name === normalizedName)) {
    window.alert(`Session name '${normalizedName}' is already in use.`)
    return
  }

  try {
    const updatedSession = await renameSession(session.port, normalizedName)
    manager.upsertDaemonSession(updatedSession)
  } catch (err) {
    window.alert(err instanceof Error ? err.message : 'Failed to rename session')
  }
}

async function handleDragEnd(event: { canceled: boolean; operation?: { source?: { id?: number | string }; target?: { id?: number | string } | null } }): Promise<void> {
  if (event.canceled) {
    return
  }

  const sourcePort = Number(event.operation?.source?.id)
  const targetPort = Number(event.operation?.target?.id)
  if (!Number.isFinite(sourcePort) || !Number.isFinite(targetPort) || sourcePort === targetPort) {
    return
  }

  const currentPorts = manager.sessionList.map(session => session.port)
  const fromIndex = currentPorts.indexOf(sourcePort)
  const toIndex = currentPorts.indexOf(targetPort)
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) {
    return
  }

  const nextPorts = [...currentPorts]
  const [movedPort] = nextPorts.splice(fromIndex, 1)
  nextPorts.splice(toIndex, 0, movedPort)
  manager.applySessionOrder(nextPorts)

  try {
    const result = await reorderSessions(nextPorts)
    manager.reconcileSessions(result.sessions)
  } catch (err) {
    console.error('Failed to reorder sessions:', err)
    await refreshSessions()
  }
}

function openNewSessionModal(): void {
  newSessionPath.value = defaultSessionPath.value
  selectedShell.value = shellOptions.value.some(option => option.type === defaultShell.value)
    ? defaultShell.value
    : shellOptions.value[0]?.type ?? ''
  createError.value = ''
  showNewSessionModal.value = true
  ui.closeMobileNav()
}

function closeNewSessionModal(): void {
  if (isCreatingSession.value) return
  showNewSessionModal.value = false
  newSessionPath.value = ''
  createError.value = ''
}

function openHome(): void {
  router.push('/')
  ui.closeMobileNav()
}

function openSettingsModal(): void {
  if (settingsSaveCloseTimer !== null) {
    window.clearTimeout(settingsSaveCloseTimer)
    settingsSaveCloseTimer = null
  }
  settingsPreviewSnapshot.value = {
    managerThemePreset: ui.managerThemePreset,
    terminalThemePreset: ui.terminalThemePreset,
  }
  settingsSaveState.value = 'idle'
  settingsSaveError.value = ''
  showSettingsModal.value = true
  ui.closeMobileNav()
}

function openBulkCommandModal(): void {
  bulkCommandError.value = ''
  showBulkCommandModal.value = true
  ui.closeMobileNav()
}

function closeBulkCommandModal(): void {
  if (isRunningBulkCommand.value) {
    return
  }

  bulkCommandError.value = ''
  showBulkCommandModal.value = false
}

async function handleBulkCommand(action: (typeof bulkCommandActions)[number]): Promise<void> {
  if (isRunningBulkCommand.value) {
    return
  }

  isRunningBulkCommand.value = true
  bulkCommandError.value = ''

  try {
    await action.run()
    await refreshSessions()
    showBulkCommandModal.value = false
  } catch (err) {
    bulkCommandError.value = err instanceof Error ? err.message : `Failed to run ${action.label}`
  } finally {
    isRunningBulkCommand.value = false
  }
}

function closeSettingsModal(): void {
  if (settingsSaveCloseTimer !== null) {
    window.clearTimeout(settingsSaveCloseTimer)
    settingsSaveCloseTimer = null
  }
  ui.previewAppearanceSettings(settingsPreviewSnapshot.value)
  settingsSaveState.value = 'idle'
  settingsSaveError.value = ''
  showSettingsModal.value = false
}

function handlePreviewAppearanceSettings(payload: {
  managerThemePreset?: ThemePresetName
  terminalThemePreset?: ThemePresetName
}): void {
  ui.previewAppearanceSettings(payload)
}

async function handleSaveAppearanceSettings(payload: {
  managerThemePreset: ThemePresetName
  terminalThemePreset: ThemePresetName
  fontSize: number
  lineHeight: number
}): Promise<void> {
  if (settingsSaveState.value === 'saving') {
    return
  }

  if (settingsSaveCloseTimer !== null) {
    window.clearTimeout(settingsSaveCloseTimer)
    settingsSaveCloseTimer = null
  }

  settingsSaveState.value = 'saving'
  settingsSaveError.value = ''

  try {
    await ui.setAppearanceSettings(payload)
    settingsPreviewSnapshot.value = {
      managerThemePreset: payload.managerThemePreset,
      terminalThemePreset: payload.terminalThemePreset,
    }
    settingsSaveState.value = 'success'
    settingsSaveCloseTimer = window.setTimeout(() => {
      settingsSaveCloseTimer = null
      closeSettingsModal()
    }, 250)
  } catch (err) {
    settingsSaveState.value = 'failure'
    settingsSaveError.value = err instanceof Error ? err.message : 'Failed to save settings'
  }
}

function toggleShareDetails(): void {
  showShareDetails.value = !showShareDetails.value
}

// Normalize path for cross-platform compatibility
function normalizePath(path: string): string {
  if (!path) return ''
  // Trim whitespace
  path = path.trim()
  // Normalize separators - handle both forward and backslashes
  // On Windows, normalize to backslashes; on Unix, forward slashes
  if (navigator.platform.toLowerCase().includes('win')) {
    // Windows: normalize to backslashes, handle mixed separators
    path = path.replace(/\//g, '\\')
    // Remove duplicate backslashes
    path = path.replace(/\\+/g, '\\')
  } else {
    // Unix: normalize to forward slashes
    path = path.replace(/\\/g, '/')
    path = path.replace(/\/+/g, '/')
  }
  return path
}

async function handleCreateNewSession(): Promise<void> {
  if (isCreatingSession.value) return

  try {
    isCreatingSession.value = true
    createError.value = ''
    const cwd = normalizePath(newSessionPath.value)
    const shell = shellOptions.value.some(option => option.type === selectedShell.value)
      ? selectedShell.value
      : ''
    const data = await createSession({
      ...(cwd ? { cwd } : {}),
      ...(shell ? { shell } : {}),
    })
    isCreatingSession.value = false
    closeNewSessionModal()
    router.push(`/${data.port}`)
  } catch (err) {
    console.error('Failed to create session:', err)
    createError.value = err instanceof Error ? err.message : 'Failed to create session'
  } finally {
    isCreatingSession.value = false
  }
}

// Resize handling
function startResize(e: MouseEvent): void {
  e.preventDefault()
  isResizing.value = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
}

function handleResize(e: MouseEvent): void {
  if (!isResizing.value) return
  ui.setSidebarWidth(e.clientX)
}

function stopResize(): void {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

onUnmounted(() => {
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  if (settingsSaveCloseTimer !== null) {
    window.clearTimeout(settingsSaveCloseTimer)
    settingsSaveCloseTimer = null
  }
})

async function fetchSessions(): Promise<void> {
  try {
    const data = await listSessions()
    manager.reconcileSessions(data)
  } catch (err) {
    console.error('Failed to fetch sessions:', err)
  }
}

async function refreshSessions(): Promise<void> {
  await fetchSessions()
}

async function fetchDefaults(): Promise<void> {
  try {
    const defaults = await getDefaults()
    defaultSessionPath.value = normalizePath(defaults.cwd)
    defaultShell.value = defaults.shell
    shellOptions.value = defaults.shell_options
    selectedShell.value = defaults.shell_options.some(option => option.type === defaults.shell)
      ? defaults.shell
      : defaults.shell_options[0]?.type ?? defaults.shell
    shareMode.value = defaults.share_mode
    shareUrl.value = defaults.manager_url

    if (defaults.share_mode && defaults.manager_url) {
      shareQrCode.value = await QRCode.toDataURL(defaults.manager_url, {
        width: 164,
        margin: 1,
        color: {
          dark: '#111111',
          light: '#facc15',
        },
      })
    } else {
      shareQrCode.value = ''
    }
  } catch (err) {
    console.error('Failed to fetch defaults:', err)
  }
}

async function copyShareUrl(): Promise<void> {
  if (!shareUrl.value) return
  try {
    await navigator.clipboard.writeText(shareUrl.value)
  } catch (err) {
    console.error('Failed to copy share URL:', err)
  }
}

function handlePanelToggle(): void {
  if (window.matchMedia('(min-width: 768px)').matches) {
    ui.toggleSidebar()
    return
  }

  ui.closeMobileNav()
}

onMounted(() => {
  void fetchSessions()
  void fetchDefaults()
})

watch(
  () => route.fullPath,
  () => {
    ui.closeMobileNav()
  },
)
</script>

<template>
  <div
    v-if="ui.isMobileNavOpen"
    class="fixed inset-0 z-40 bg-[var(--color-backdrop)] backdrop-blur-sm md:hidden"
    @click="ui.closeMobileNav"
  ></div>

  <aside
      class="fixed inset-y-0 left-0 z-50 flex h-full shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-secondary)] shadow-[0_12px_32px_var(--color-shadow)] transition-transform duration-300 md:static md:z-auto md:shadow-none"
    :class="ui.isMobileNavOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
    :style="sidebarWidthStyle"
  >
    <div class="flex flex-col overflow-hidden border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div v-if="!ui.isSidebarCollapsed" class="flex items-center justify-between gap-3 px-3 py-2">
        <div class="min-w-0 overflow-hidden">
          <p class="truncate text-xs font-medium uppercase tracking-[0.24em] text-[var(--color-text-muted)]">
            Silk Manager
            <span class="ml-2 normal-case tracking-normal text-[var(--color-text-secondary)]">{{ sessions.length }}</span>
          </p>
        </div>

        <button
          @click="openSettingsModal"
          class="bar-button icon-button bar-button-tight border border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
          title="Open settings"
          aria-label="Open settings"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" class="toolbar-icon" aria-hidden="true">
            <path d="M6.25 2.5h3.5l.35 1.45a4.9 4.9 0 0 1 1.1.45l1.34-.75 2 2-1.01 1.27c.16.35.29.72.38 1.1L15.5 8l-.1 2-1.45.35a4.9 4.9 0 0 1-.45 1.1l.75 1.34-2 2-1.27-1.01a5.7 5.7 0 0 1-1.1.38L9.75 15.5h-3.5l-.35-1.45a4.9 4.9 0 0 1-1.1-.45l-1.34.75-2-2 1.01-1.27a5.7 5.7 0 0 1-.38-1.1L.5 10l.1-2 1.45-.35a4.9 4.9 0 0 1 .45-1.1L1.75 5.2l2-2 1.27 1.01a5.7 5.7 0 0 1 1.1-.38L6.25 2.5Z" />
            <circle cx="8" cy="8" r="2.1" />
          </svg>
        </button>
      </div>

      <div v-else class="flex items-center justify-center gap-2 border-t border-[var(--color-border)] px-1 py-2">
        <button
          @click="openSettingsModal"
          class="bar-button icon-button border border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
          title="Open settings"
          aria-label="Open settings"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" class="toolbar-icon" aria-hidden="true">
            <path d="M6.25 2.5h3.5l.35 1.45a4.9 4.9 0 0 1 1.1.45l1.34-.75 2 2-1.01 1.27c.16.35.29.72.38 1.1L15.5 8l-.1 2-1.45.35a4.9 4.9 0 0 1-.45 1.1l.75 1.34-2 2-1.27-1.01a5.7 5.7 0 0 1-1.1.38L9.75 15.5h-3.5l-.35-1.45a4.9 4.9 0 0 1-1.1-.45l-1.34.75-2-2 1.01-1.27a5.7 5.7 0 0 1-.38-1.1L.5 10l.1-2 1.45-.35a4.9 4.9 0 0 1 .45-1.1L1.75 5.2l2-2 1.27 1.01a5.7 5.7 0 0 1 1.1-.38L6.25 2.5Z" />
            <circle cx="8" cy="8" r="2.1" />
          </svg>
        </button>
      </div>

      <div :class="ui.isSidebarCollapsed ? 'flex flex-col' : 'grid h-9 grid-cols-5 border-t border-[var(--color-border)]'">
        <button
          @click="openNewSessionModal"
          class="bar-button bar-button-accent w-full"
          :class="ui.isSidebarCollapsed ? 'h-11 border-b border-[var(--color-border)]' : 'h-full border-r border-[var(--color-border)]'"
          title="Create new session"
          aria-label="Create new session"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" class="toolbar-icon" aria-hidden="true">
            <path d="M8 3v10M3 8h10" />
          </svg>
        </button>

        <button
          @click="openHome"
          class="bar-button w-full"
          :class="ui.isSidebarCollapsed ? 'h-11 border-b border-[var(--color-border)]' : 'h-full border-r border-[var(--color-border)]'"
          title="Home"
          aria-label="Home"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" class="toolbar-icon" aria-hidden="true">
            <path d="M2.5 7.5 8 3l5.5 4.5" />
            <path d="M4.5 6.8V13h7V6.8" />
          </svg>
        </button>

        <button
          @click="ui.toggleTheme"
          class="bar-button w-full"
          :class="ui.isSidebarCollapsed ? 'h-11 border-b border-[var(--color-border)]' : 'h-full border-r border-[var(--color-border)]'"
          :title="`Switch to ${ui.resolvedTheme === 'dark' ? 'light' : 'dark'} theme`"
          aria-label="Toggle theme"
        >
          <svg
            v-if="ui.resolvedTheme === 'dark'"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            class="toolbar-icon"
            aria-hidden="true"
          >
            <circle cx="8" cy="8" r="2.8" />
            <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4" />
          </svg>
          <svg
            v-else
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            class="toolbar-icon"
            aria-hidden="true"
          >
            <path d="M10.8 1.9a5.9 5.9 0 1 0 3.3 10.8A6.4 6.4 0 0 1 10.8 1.9Z" />
          </svg>
        </button>

        <button
          @click="refreshSessions"
          class="bar-button w-full"
          :class="ui.isSidebarCollapsed ? 'h-11 border-b border-[var(--color-border)]' : 'h-full border-r border-[var(--color-border)]'"
          title="Refresh session list"
          aria-label="Refresh session list"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.45" class="toolbar-icon" aria-hidden="true">
            <path d="M13 4v3h-3" />
            <path d="M3 12V9h3" />
            <path d="M12.6 6.25A5.1 5.1 0 0 0 4.55 4.7L3 7M13 8a5 5 0 0 1-8.45 3.55L3 9" />
          </svg>
        </button>

        <button
          @click="handlePanelToggle"
          class="bar-button w-full text-[var(--color-text-secondary)]"
          :class="ui.isSidebarCollapsed ? 'h-11 border-b border-[var(--color-border)]' : 'h-full'"
          :title="ui.isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :aria-label="ui.isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        >
          <span class="text-sm leading-none">{{ ui.isSidebarCollapsed ? '›' : '‹' }}</span>
        </button>
      </div>
    </div>

      <div class="soft-scrollbar flex-1 overflow-y-auto" :class="ui.isSidebarCollapsed ? 'p-1' : ''">
        <DragDropProvider @dragEnd="handleDragEnd">
          <div v-if="!ui.isSidebarCollapsed" class="border-b border-[var(--color-border)]">
            <SidebarSessionRow
              v-for="session in sessions"
              :key="session.port"
              :session="session"
              :selected="manager.focusedPort === session.port"
              @select="selectSession(session.port)"
              @rename="handleRenameSession(session)"
            />
          </div>

          <div v-else class="flex flex-col gap-1">
            <SidebarSessionRow
              v-for="session in sessions"
              :key="session.port"
              :session="session"
              compact
              :selected="manager.focusedPort === session.port"
              @select="selectSession(session.port)"
              @rename="handleRenameSession(session)"
            />
          </div>
        </DragDropProvider>
      </div>

      <div v-if="!ui.isSidebarCollapsed" class="border-t border-[var(--color-border)] p-2.5">
        <button
          @click="openBulkCommandModal"
          class="mb-2 w-full border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2.5 py-2 text-left text-sm font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-bg-hover)]"
        >
          Bulk Command
        </button>
        <template v-if="shareMode && shareUrl">
          <button
            class="flex w-full items-center justify-between border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2.5 py-2 text-left transition-colors hover:bg-[var(--color-bg-hover)]"
            @click="toggleShareDetails"
          >
            <span class="text-[11px] font-bold uppercase tracking-[0.24em] text-[var(--color-accent)]">LAN Share</span>
            <span class="text-xs text-[var(--color-text-secondary)]">{{ showShareDetails ? 'Hide' : 'Show' }}</span>
          </button>
          <div v-if="showShareDetails" class="pt-2">
            <p class="text-xs leading-5 text-[var(--color-text-secondary)]">
              Anybody on your network can open this manager and poke your shells.
            </p>
            <img
              v-if="shareQrCode"
              :src="shareQrCode"
              alt="QR code for manager LAN URL"
              class="mx-auto mt-2 h-32 w-32 border border-[var(--color-border)] bg-white p-2"
            />
            <button
              @click="copyShareUrl"
              class="mt-2 w-full border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2.5 py-2 text-left text-xs text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-bg-hover)]"
              :title="shareUrl"
            >
              {{ shareUrl }}
            </button>
          </div>
        </template>

        <div v-else class="space-y-1">
          <p class="text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-muted)]">
            Local mode
          </p>
          <p class="text-[10px] leading-4 text-[var(--color-text-secondary)]">
            QR sharing is off. Restart the daemon in shared mode to show the QR and allow LAN access.
          </p>
        </div>

        <div class="mt-2 border-t border-[var(--color-border)] pt-2">
          <p class="text-[10px] leading-4 text-[var(--color-text-muted)]">
            Built {{ builtVersion }}
          </p>
        </div>
      </div>

      <div
        v-if="!ui.isSidebarCollapsed"
        class="absolute right-0 top-0 hidden h-full w-1 cursor-col-resize transition-colors hover:bg-[var(--color-accent-muted)] md:block"
        :class="{ 'bg-[var(--color-accent-muted)]': isResizing }"
        data-testid="sidebar-resize-handle"
        @mousedown="startResize"
      ></div>
  </aside>

    <!-- New Session Modal -->
    <Teleport to="body">
      <div
        v-if="showNewSessionModal"
        class="fixed inset-0 z-[60] flex items-center justify-center bg-[var(--color-backdrop)] px-4"
        @click.self="closeNewSessionModal"
      >
      <div class="glass-panel w-full max-w-md p-4">
          <h3 class="mb-4 font-[var(--font-display)] text-2xl text-[var(--color-accent)]">New Session</h3>
          <div class="mb-4">
            <label class="mb-2 block text-sm text-[var(--color-text-secondary)]">Shell</label>
            <div class="grid gap-2">
              <button
                v-for="shell in shellOptions"
                :key="shell.type"
                type="button"
                class="flex items-center justify-between border px-3 py-2 text-left transition-colors"
                :class="selectedShell === shell.type
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-muted)]'
                  : 'border-[var(--color-border)] bg-[var(--color-bg-primary)] hover:bg-[var(--color-bg-hover)]'"
                @click="selectedShell = shell.type"
              >
                <div class="min-w-0">
                  <div class="text-sm font-medium text-[var(--color-text-primary)]">{{ shell.label }}</div>
                  <div class="truncate text-[10px] text-[var(--color-text-muted)]">{{ shell.path }}</div>
                </div>
                <span v-if="shell.type === defaultShell" class="ml-3 shrink-0 text-[10px] uppercase tracking-[0.2em] text-[var(--color-accent)]">
                  Default
                </span>
              </button>
            </div>
            <p v-if="shellOptions.length === 0" class="mt-2 text-xs text-[var(--color-text-muted)]">
              No shell choices detected.
            </p>
          </div>
          <div class="mb-4">
            <label class="mb-2 block text-sm text-[var(--color-text-secondary)]">Working Directory (optional)</label>
            <input
              v-model="newSessionPath"
              type="text"
              class="w-full border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-accent)]"
              :placeholder="defaultSessionPath || 'e.g., /home/user/project or C:\\Users\\project'"
              :disabled="isCreatingSession"
              @keydown.enter="handleCreateNewSession"
              @keydown.esc="closeNewSessionModal"
              autofocus
            />
            <p class="mt-2 text-xs text-[var(--color-text-muted)]">
              Defaults to your home directory on the daemon machine.
            </p>
            <p v-if="isCreatingSession" class="mt-2 text-xs text-[var(--color-accent)]">
              Creating `{{ selectedShellLabel }}`{{ newSessionPath.trim() ? ` in ${newSessionPath.trim()}` : '' }}...
            </p>
            <p v-else class="mt-2 text-xs text-[var(--color-text-muted)]">
              Shell: `{{ selectedShellLabel }}`
            </p>
            <p v-if="createError" class="mt-2 text-xs text-[var(--color-error)]">{{ createError }}</p>
          </div>
          <div class="flex justify-end">
            <div class="toolbar-strip">
              <button @click="closeNewSessionModal" class="bar-button text-sm" :disabled="isCreatingSession">Cancel</button>
              <button @click="handleCreateNewSession" class="bar-button bar-button-accent text-sm font-medium" :disabled="isCreatingSession">
                {{ isCreatingSession ? 'Creating...' : 'Create' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showBulkCommandModal"
        class="fixed inset-0 z-[60] flex items-center justify-center bg-[var(--color-backdrop)] px-4"
        @click.self="closeBulkCommandModal"
      >
        <div class="glass-panel w-full max-w-md p-4">
          <h3 class="mb-2 font-[var(--font-display)] text-2xl text-[var(--color-accent)]">Bulk Command</h3>
          <p class="mb-4 text-sm text-[var(--color-text-secondary)]">
            Apply one command across every listed session.
          </p>
          <div class="grid gap-2">
            <button
              v-for="action in bulkCommandActions"
              :key="action.label"
              type="button"
              class="flex items-center justify-between border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-3 py-2 text-left text-sm text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-bg-hover)]"
              :disabled="isRunningBulkCommand"
              @click="handleBulkCommand(action)"
            >
              <span>{{ action.label }}</span>
              <span class="text-[10px] uppercase tracking-[0.2em] text-[var(--color-text-muted)]">All Sessions</span>
            </button>
          </div>
          <p v-if="bulkCommandError" class="mt-3 text-xs text-[var(--color-error)]">{{ bulkCommandError }}</p>
          <div class="mt-4 flex justify-end">
            <div class="toolbar-strip">
              <button @click="closeBulkCommandModal" class="bar-button text-sm" :disabled="isRunningBulkCommand">Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <ManagerSettingsModal
      :open="showSettingsModal"
      :manager-theme-preset="ui.managerThemePreset"
      :terminal-theme-preset="ui.terminalThemePreset"
      :font-size="ui.terminalDefaults.fontSize"
      :line-height="ui.terminalDefaults.lineHeight"
      :save-state="settingsSaveState"
      :save-error="settingsSaveError"
      @close="closeSettingsModal"
      @preview="handlePreviewAppearanceSettings"
      @save="handleSaveAppearanceSettings"
    />
</template>
