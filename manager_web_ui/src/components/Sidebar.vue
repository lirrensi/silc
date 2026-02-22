<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalManager } from '@/stores/terminalManager'
import { listSessions, createSession } from '@/lib/daemonApi'

const router = useRouter()
const manager = useTerminalManager()

const sessions = computed(() => manager.sessionList)

// Sidebar width state (resizable)
const sidebarWidth = ref(220)
const isResizing = ref(false)
const minWidth = 180
const maxWidth = 400

// New session modal state
const showNewSessionModal = ref(false)
const newSessionPath = ref('')

function statusColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-[#4ade80]'
    case 'idle': return 'bg-[#6b7280]'
    case 'dead': return 'bg-[#f87171]'
    default: return 'bg-[#6b7280]'
  }
}

function selectSession(port: number): void {
  router.push(`/${port}`)
}

function openNewSessionModal(): void {
  newSessionPath.value = ''
  showNewSessionModal.value = true
}

function closeNewSessionModal(): void {
  showNewSessionModal.value = false
  newSessionPath.value = ''
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
  try {
    const cwd = normalizePath(newSessionPath.value)
    const data = await createSession(cwd ? { cwd } : undefined)
    await fetchSessions()
    closeNewSessionModal()
    router.push(`/${data.port}`)
  } catch (err) {
    console.error('Failed to create session:', err)
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
    // Sync sessions with daemon
    for (const daemonSession of data) {
      if (!manager.getSession(daemonSession.port)) {
        manager.createSession(daemonSession.port, daemonSession.session_id, daemonSession.shell, daemonSession.name, daemonSession.cwd)
      }
    }
  } catch (err) {
    console.error('Failed to fetch sessions:', err)
  }
}

// Fetch on mount
fetchSessions()
</script>

<template>
  <aside
    class="bg-[#252526] border-r border-[#5e5e62] flex flex-col h-full relative"
    :style="{ width: `${sidebarWidth}px` }"
  >
    <!-- Header -->
    <div class="p-3 border-b border-[#5e5e62] flex gap-2">
      <button
        @click="openNewSessionModal"
        class="flex-1 px-3 py-2 bg-[#ff80bf] hover:bg-[#ff99cc] text-black font-medium rounded transition-colors text-sm"
        title="Create new session"
      >
        +
      </button>
      <button
        @click="router.push('/')"
        class="px-3 py-2 bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors text-sm"
        title="Home"
      >
        🏠
      </button>
    </div>

    <!-- Session List -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="session in sessions"
        :key="session.port"
        @click="selectSession(session.port)"
        class="flex items-center gap-2 px-3 py-2 hover:bg-[#3d3d3d] cursor-pointer transition-colors"
        :class="{ 'bg-[#3d3d3d]': manager.focusedPort === session.port }"
      >
        <div class="w-2 h-2 rounded-full flex-shrink-0" :class="statusColor(session.status)"></div>
        <span class="text-sm truncate flex-1">{{ session.name || 'unnamed' }}</span>
        <span class="text-xs text-[#6b7280] font-mono flex-shrink-0">:{{ session.port }}</span>
      </div>
    </div>

    <!-- Resize Handle -->
    <div
      class="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-[#ff80bf]/30 transition-colors"
      :class="{ 'bg-[#ff80bf]/50': isResizing }"
      @mousedown="startResize"
    ></div>

    <!-- New Session Modal -->
    <Teleport to="body">
      <div
        v-if="showNewSessionModal"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="closeNewSessionModal"
      >
        <div class="bg-[#252526] border border-[#5e5e62] rounded-lg p-4 w-96 max-w-[90vw]">
          <h3 class="text-lg font-medium text-[#ff80bf] mb-4">New Session</h3>
          <div class="mb-4">
            <label class="block text-sm text-[#a0a0a0] mb-2">Working Directory (optional)</label>
            <input
              v-model="newSessionPath"
              type="text"
              class="w-full px-3 py-2 bg-[#1e1e1e] border border-[#5e5e62] rounded text-white text-sm focus:outline-none focus:border-[#ff80bf]"
              placeholder="e.g., /home/user/project or C:\Users\project"
              @keydown.enter="handleCreateNewSession"
              @keydown.esc="closeNewSessionModal"
              autofocus
            />
          </div>
          <div class="flex gap-2 justify-end">
            <button
              @click="closeNewSessionModal"
              class="px-4 py-2 text-sm bg-[#3e3e42] hover:bg-[#5e5e62] border border-[#5e5e62] rounded transition-colors"
            >
              Cancel
            </button>
            <button
              @click="handleCreateNewSession"
              class="px-4 py-2 text-sm bg-[#ff80bf] hover:bg-[#ff99cc] text-black font-medium rounded transition-colors"
            >
              Create
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </aside>
</template>
