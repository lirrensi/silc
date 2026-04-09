<script setup lang="ts">
// FILE: manager_web_ui/src/components/SessionShell.vue
// PURPOSE: Render the shared single-session terminal shell with recovery actions and lifecycle controls.
// OWNS: Session terminal layout, action bar, reconnect/takeover state, command summary, and session bootstrapping.
// EXPORTS: SessionShell - reusable single-session terminal surface.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md, agent_chat/plan_session_end_splash_2026-04-09.md

import { computed } from 'vue'
import { useSessionShell } from '@/composables/useSessionShell'
import TerminalViewport from '@/components/TerminalViewport.vue'

const props = defineProps<{
  port: number
  surface: 'manager' | 'standalone'
}>()

const emit = defineEmits<{
  exit: []
  'port-change': [port: number]
}>()

const {
  port,
  session,
  isDormant,
  isRestarting,
  reconnecting,
  activeOperation,
  terminalEndState,
  hasConnectionProblem,
  controlsDisabled,
  disconnectReason,
  connectionLabel,
  tip,
  handleRefresh,
  handleClose,
  handleUnload,
  handleKill,
  handleRestart,
  handleReconnect,
  closeWindow,
  handleInterrupt,
  handleSigterm,
  handleSigkill,
  handleClear,
  handlePaste,
  handleBottom,
  sendArrowKey,
} = useSessionShell(
  computed(() => props.port),
  props.surface,
  () => emit('exit'),
  (port) => emit('port-change', port),
)

function summarizeCommand(commandText: string): string {
  return commandText.replace(/\s+/g, ' ').trim().slice(0, 72)
}

async function copyCommand(commandText: string | null | undefined): Promise<void> {
  const text = commandText?.trim()
  if (!text || !navigator.clipboard?.writeText) return
  try {
    await navigator.clipboard.writeText(text)
  } catch (err) {
    console.error('Failed to copy session command:', err)
  }
}

const commandSummary = computed(() => {
  const text = session.value?.command?.text?.trim()
  return text ? summarizeCommand(text) : ''
})
</script>

<template>
  <div class="session-view h-full flex flex-col">
    <div
      class="tab-bar flex min-h-[2.0rem] items-stretch justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
    >
      <div class="min-w-0 flex flex-1 items-center gap-2 overflow-hidden px-3 py-1.5 md:px-4">
        <span class="truncate text-sm font-medium text-[var(--color-accent)]">{{ session?.name || 'unnamed' }}</span>
        <span class="shrink-0 font-mono text-xs text-[var(--color-text-muted)]">:{{ port }}</span>
        <span class="shrink-0 text-xs text-[var(--color-text-muted)]">[{{ session?.shell ?? '' }}]</span>
        <span
          v-if="session?.cwd"
          class="truncate text-xs text-[var(--color-text-secondary)]"
          :title="session.cwd"
        >
          {{ session.cwd }}
        </span>
        <span class="truncate text-xs text-[var(--color-text-muted)]">{{ session?.title || '—' }}</span>
        <span
          v-if="commandSummary"
          class="truncate cursor-copy text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
          :title="session?.command?.text ? `Click to copy command: ${session.command.text}` : undefined"
          role="button"
          tabindex="0"
          @click="copyCommand(session?.command?.text)"
          @keydown.enter.prevent="copyCommand(session?.command?.text)"
          @keydown.space.prevent="copyCommand(session?.command?.text)"
        >
          {{ commandSummary }}
        </span>
      </div>
      <div
        class="bar-actions bar-actions-session-lifecycle shrink-0 border-l border-[var(--color-border)]"
      >
        <button
          @click="handleUnload"
          class="bar-button bar-button-lifecycle bar-button-tight text-xs"
          :title="
            tip(
              'Unload this session',
              'Releases the live shell while keeping the saved session record available.',
            )
          "
          :disabled="activeOperation !== null"
        >
          Unload
        </button>
        <button
          @click="handleRestart"
          class="bar-button bar-button-lifecycle bar-button-tight bar-button-info text-xs"
          :title="tip('Restart the session', 'Recreates the shell and reconnects the browser to it.')"
          :disabled="activeOperation !== null || isRestarting"
        >
          Restart
        </button>
        <button
          @click="handleClose"
          class="bar-button bar-button-lifecycle bar-button-tight text-xs"
          :title="
            tip(
              'Close this session gracefully',
              'Asks the daemon to shut the session down and return home.',
            )
          "
          :disabled="activeOperation !== null"
        >
          Close Session
        </button>
        <button
          @click="handleKill"
          class="bar-button bar-button-lifecycle bar-button-tight bar-button-danger text-xs"
          :title="
            tip(
              'Force-kill this session',
              'Use when graceful close is not enough or the shell is wedged.',
            )
          "
          :disabled="activeOperation !== null"
        >
          Close Forcefully
        </button>
      </div>
    </div>

    <div class="relative min-h-0 flex-1 overflow-hidden">
      <div
        v-if="isDormant"
        class="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--color-bg-primary)_74%,transparent)] px-4"
      >
        <div class="glass-panel flex w-full max-w-md flex-col gap-3 p-4 text-center">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">Waking session</p>
          <p class="text-xs text-[var(--color-text-secondary)]">
            The session is being materialized before interaction continues.
          </p>
        </div>
      </div>
      <div
        :class="hasConnectionProblem ? 'pointer-events-none h-full grayscale opacity-55' : 'h-full'"
      >
        <TerminalViewport :port="port" :interactive="true" />
      </div>
      <div
        v-if="activeOperation"
        class="pointer-events-none absolute right-3 top-3 z-20 w-[min(28rem,calc(100%-1.5rem))]"
      >
        <div
          class="glass-panel pointer-events-auto flex items-center justify-between gap-3 px-3 py-2 shadow-lg"
        >
          <div class="min-w-0">
            <p class="text-[10px] uppercase tracking-[0.3em] text-[var(--color-text-muted)]">
              Processing
            </p>
            <p class="truncate text-sm font-medium text-[var(--color-text-primary)]">
              {{ activeOperation.label }}
            </p>
            <p class="text-xs text-[var(--color-text-secondary)]">{{ activeOperation.stage }}</p>
            <p class="text-xs text-[var(--color-text-muted)]">{{ activeOperation.detail }}</p>
          </div>
          <div
            class="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full"
            :class="activeOperation.tone === 'danger' ? 'bg-red-400' : 'bg-[var(--color-accent)]'"
          ></div>
        </div>
      </div>
      <div
        v-if="hasConnectionProblem"
        class="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--color-bg-primary)_74%,transparent)] px-4"
      >
        <div class="glass-panel flex w-full max-w-md flex-col gap-3 p-4 text-center">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">{{ connectionLabel }}</p>
          <p v-if="disconnectReason" class="text-xs text-[var(--color-text-secondary)]">
            {{ disconnectReason }}
          </p>
          <p class="text-xs text-[var(--color-text-secondary)]">
            Port `:{{ port }}` is not interactive until the websocket comes back.
          </p>
          <div class="mx-auto toolbar-strip">
            <button
              @click="handleReconnect"
              class="bar-button text-sm"
              :title="
                tip(
                  'Reconnect to the session',
                  'Reopens the websocket when the shell is still alive.',
                )
              "
              :disabled="reconnecting || isRestarting"
            >
              {{ reconnecting ? 'Reconnecting...' : 'Reconnect' }}
            </button>
            <button
              @click="handleRestart"
              class="bar-button bar-button-info text-sm"
              :title="
                tip('Restart the session', 'Recreates the shell and reconnects the browser to it.')
              "
              :disabled="reconnecting || isRestarting"
            >
              {{ isRestarting ? 'Restarting...' : 'Restart' }}
            </button>
          </div>
        </div>
      </div>
      <div
        v-if="terminalEndState"
        class="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--color-bg-primary)_74%,transparent)] px-4"
      >
        <div class="glass-panel flex w-full max-w-md flex-col gap-3 p-4 text-center">
          <p class="text-sm font-medium text-[var(--color-text-primary)]">{{ terminalEndState.title }}</p>
          <p class="text-xs text-[var(--color-text-secondary)]">{{ terminalEndState.detail }}</p>
          <p class="text-xs text-[var(--color-text-secondary)]">
            The session ended on port `:{{ port }}` and this page can now be closed.
          </p>
          <div class="mx-auto toolbar-strip">
            <button
              @click="closeWindow"
              class="bar-button text-sm"
              :title="tip('Close this window', 'Closes the standalone session page after the shell ends.')"
            >
              Close Window
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      class="control-bar soft-scrollbar shrink-0 overflow-x-auto border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)]"
    >
      <div class="flex min-h-[2.1rem] min-w-max items-stretch">
        <div class="flex items-stretch">
          <button
            @click="handleRefresh"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="
              tip('Refresh the buffer', 'Reloads the current screen state from the daemon history.')
            "
            :disabled="controlsDisabled"
          >
            Refresh
          </button>
          <button
            @click="handleBottom"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Jump to the bottom', 'Scrolls the viewport to the newest output line.')"
            :disabled="controlsDisabled"
          >
            Bottom
          </button>
          <button
            @click="sendArrowKey('\x1b[A')"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Send Up Arrow', 'Useful for shell history and command-line navigation.')"
            :disabled="controlsDisabled"
          >
            ↑
          </button>
          <button
            @click="sendArrowKey('\x1b[D')"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Send Left Arrow', 'Moves the cursor one character to the left.')"
            :disabled="controlsDisabled"
          >
            ←
          </button>
          <button
            @click="sendArrowKey('\x1b[B')"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Send Down Arrow', 'Moves through command history or lists.')"
            :disabled="controlsDisabled"
          >
            ↓
          </button>
          <button
            @click="sendArrowKey('\x1b[C')"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Send Right Arrow', 'Moves the cursor one character to the right.')"
            :disabled="controlsDisabled"
          >
            →
          </button>
          <button
            @click="handlePaste"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="
              tip(
                'Paste from clipboard',
                'Reads clipboard text and sends it straight to the shell.',
              )
            "
            :disabled="controlsDisabled"
          >
            Paste
          </button>
        </div>
        <div class="flex-1"></div>
        <div class="flex items-stretch">
          <button
            @click="handleClear"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="
              tip('Clear the terminal', 'Clears the session output/history without restarting the shell.')
            "
            :disabled="controlsDisabled"
          >
            Clear
          </button>
          <button
            @click="handleInterrupt"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="tip('Send SIGINT', 'Equivalent to Ctrl+C for the foreground process.')"
            :disabled="controlsDisabled"
          >
            SIGINT
          </button>
          <button
            @click="handleSigterm"
            class="bar-button bar-button-tight border-r border-[var(--color-border)] text-xs"
            :title="
              tip('Send SIGTERM', 'Requests a graceful shutdown from the shell process group.')
            "
            :disabled="controlsDisabled"
          >
            SIGTERM
          </button>
          <button
            @click="handleSigkill"
            class="bar-button bar-button-tight bar-button-danger border-r border-[var(--color-border)] text-xs"
            :title="tip('Send SIGKILL', 'Forcibly terminates the foreground process immediately.')"
            :disabled="controlsDisabled"
          >
            SIGKILL
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
