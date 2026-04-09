<script setup lang="ts">
// FILE: manager_web_ui/src/views/SessionView.vue
// PURPOSE: Adapt the shared session shell to the manager router and keep session navigation local.
// OWNS: Route-param to port resolution and session-shell exit/port-change routing.
// EXPORTS: SessionView - routed manager-session page wrapper.
// DOCS: agent_chat/plan_web_shell_split_2026-04-09.md

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SessionShell from '@/components/SessionShell.vue'

const props = defineProps<{
  port?: number
}>()

const route = useRoute()
const router = useRouter()

const sessionPort = computed(() => {
  if (Number.isFinite(props.port)) {
    return props.port as number
  }

  const routePort = Number.parseInt(String(route.params.port ?? ''), 10)
  return Number.isFinite(routePort) ? routePort : 0
})

function handleExit(): void {
  void router.replace('/')
}

function handlePortChange(port: number): void {
  void router.push(`/${port}`)
}
</script>

<template>
  <SessionShell :port="sessionPort" @exit="handleExit" @port-change="handlePortChange" />
</template>
