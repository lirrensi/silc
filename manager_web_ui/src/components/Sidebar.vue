<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import QRCode from 'qrcode'
import { useRoute, useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import { useUiStore } from '@/stores/ui'
import { listSessions, createSession, getDefaults } from '@/lib/daemonApi'
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
    width: ui.isSidebarCollapsed ? '3.75rem' : `min(${sidebarWidth.value}px, var(--shell-list-width))`,
  }
})

// Sidebar width state (resizable)
const sidebarWidth = ref(220)
const isResizing = ref(false)
const minWidth = 180
const maxWidth = 400

// New session modal state
const showNewSessionModal = ref(false)
const newSessionPath = ref('')
const defaultSessionPath = ref('')
const defaultShell = ref('shell')
const shareMode = ref(false)
const shareUrl = ref('')
const shareQrCode = ref('')
const showShareDetails = ref(false)
const isCreatingSession = ref(false)
const createError = ref('')

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'connecting': return 'bg-[#fbbf24]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    case 'restarting': return 'bg-[#0ea5e9]'
    default: return 'bg-[#6b7280]'
  }
}

function selectSession(port: number): void {
  router.push(`/${port}`)
  ui.closeMobileNav()
}

function openNewSessionModal(): void {
  newSessionPath.value = defaultSessionPath.value
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
    const data = await createSession(cwd ? { cwd } : undefined)
    await fetchSessions()
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
  const newWidth = e.clientX
  sidebarWidth.value = Math.min(maxWidth, Math.max(minWidth, newWidth))
}

function stopResize(): void {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

onUnmounted(() => {
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
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

function sessionBadgeLabel(session: Session): string {
  const name = session.name.trim()
  if (name) {
    return name.slice(0, 1).toUpperCase()
  }

  return String(session.port).slice(-1)
}

function sessionTitle(session: Session): string {
  const name = session.name || 'unnamed'
  const title = session.title || '—'
  const cwd = session.cwd || 'Home directory'
  return [name, `:${session.port}`, session.shell || 'shell', cwd, title].filter(Boolean).join(' · ')
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
    <div class="flex min-h-[5rem] flex-col overflow-hidden border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <div v-if="!ui.isSidebarCollapsed" class="flex items-center justify-between gap-3 px-3 py-2">
        <div class="min-w-0 overflow-hidden">
          <p class="truncate text-xs font-medium uppercase tracking-[0.24em] text-[var(--color-text-muted)]">
            Silk Manager
            <span class="ml-2 normal-case tracking-normal text-[var(--color-text-secondary)]">{{ sessions.length }}</span>
          </p>
        </div>
      </div>

      <div :class="ui.isSidebarCollapsed ? 'flex flex-col' : 'grid min-h-[2.4rem] grid-cols-5 border-t border-[var(--color-border)]'">
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
        <div v-if="!ui.isSidebarCollapsed" class="border-b border-[var(--color-border)]">
          <button
            v-for="session in sessions"
            :key="session.port"
            @click="selectSession(session.port)"
            class="grid w-full grid-cols-[0.5rem_minmax(0,1fr)] gap-x-2 gap-y-1 border-t border-[var(--color-border)] px-2 py-1.5 text-left transition-colors"
            :class="manager.focusedPort === session.port
              ? 'bg-[var(--color-accent-muted)]'
              : 'bg-transparent hover:bg-[var(--color-bg-hover)]'"
          >
            <div class="mt-1 h-2.5 w-2.5" :class="statusColor(session.status)"></div>
            <div class="min-w-0">
              <div class="flex items-baseline justify-between gap-2 text-sm font-medium text-[var(--color-text-primary)]">
                <span class="min-w-0 truncate">{{ session.name || 'unnamed' }}</span>
                <span class="shrink-0 font-mono text-[11px] font-normal text-[var(--color-text-muted)]">:{{ session.port }}</span>
              </div>
              <div class="mt-1 flex items-center justify-between gap-2 text-[11px] text-[var(--color-text-secondary)]">
                <span class="min-w-0 truncate">{{ session.cwd || 'Home directory' }}</span>
                <span class="shrink-0 uppercase tracking-[0.12em] text-[var(--color-text-muted)]">{{ session.shell || 'shell' }}</span>
              </div>
              <div class="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{{ session.title || '—' }}</div>
            </div>
          </button>
        </div>

        <div v-else class="flex flex-col gap-1">
          <button
            v-for="session in sessions"
            :key="session.port"
            @click="selectSession(session.port)"
            class="mx-auto flex h-9 w-9 items-center justify-center border border-[var(--color-border)] text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-primary)] transition-colors"
            :class="manager.focusedPort === session.port
              ? 'bg-[var(--color-accent-muted)]'
              : 'bg-[var(--color-bg-primary)] hover:bg-[var(--color-bg-hover)]'"
            :title="sessionTitle(session)"
            :aria-label="sessionTitle(session)"
          >
            <span class="relative flex h-4 w-4 items-center justify-center">
              <span class="h-2.5 w-2.5 rounded-full" :class="statusColor(session.status)"></span>
              <span class="absolute -bottom-2 text-[9px] leading-none text-[var(--color-text-muted)]">{{ sessionBadgeLabel(session) }}</span>
            </span>
          </button>
        </div>
      </div>

      <div v-if="shareMode && shareUrl && !ui.isSidebarCollapsed" class="border-t border-[var(--color-border)] p-2.5">
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
      </div>

      <div
        v-if="!ui.isSidebarCollapsed"
        class="absolute right-0 top-0 hidden h-full w-1 cursor-col-resize transition-colors hover:bg-[var(--color-accent-muted)] md:block"
        :class="{ 'bg-[var(--color-accent-muted)]': isResizing }"
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
              Creating `{{ defaultShell }}`{{ newSessionPath.trim() ? ` in ${newSessionPath.trim()}` : '' }}...
            </p>
            <p v-else class="mt-2 text-xs text-[var(--color-text-muted)]">
              Shell: `{{ defaultShell }}`
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
</template>
