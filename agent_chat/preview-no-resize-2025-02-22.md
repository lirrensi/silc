# Fix: Preview Cards — No PTY Resize + Bigger Cards with CSS Cover

**Date:** 2025-02-22

## Problem

1. Home page previews call `fit()` which resizes the backend PTY to tiny dimensions
2. Cards are too small (min-width 200px, fixed height 128px)
3. Switching between home and session view causes PTY resize churn

## Solution

1. **Skip `fit()` for non-interactive previews** — only resize PTY when in SessionView
2. **2×2 grid layout** — each card is 50vw × 50vh (25% of viewport)
3. **CSS "cover" scaling** — scale terminal to fill card, crop overflow

---

## Changes

### 1. `manager_web_ui/src/components/TerminalViewport.vue`

**Change:** Skip ResizeObserver and `fit()` when `interactive=false`.

```vue
// Before: ResizeObserver always set up
onMounted(() => {
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      debouncedFit(props.port)
    })
    resizeObserver.observe(containerRef.value)
  }
  // ...
})

// After: Only for interactive mode
onMounted(() => {
  // Only set up ResizeObserver for interactive terminals
  if (props.interactive && containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      debouncedFit(props.port)
    })
    resizeObserver.observe(containerRef.value)
  }
  // ...
})
```

Also update `attachAndConnect()` to only call `setFocused` when interactive (already done, but verify).

---

### 2. `manager_web_ui/src/components/SessionCard.vue`

**Changes:**
- Card size: 50vw × 50vh
- CSS cover scaling for terminal preview

```vue
<template>
  <div
    @click="handleClick"
    class="session-card relative overflow-hidden cursor-pointer hover:ring-2 hover:ring-[#ff80bf] transition-all"
  >
    <!-- Header -->
    <div class="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-3 py-2 bg-[#252526]/90 backdrop-blur-sm border-b border-[#5e5e62]">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full" :class="statusColor(session?.status ?? 'idle')"></div>
        <span class="text-sm font-medium">{{ session?.name ?? 'unnamed' }}</span>
        <span class="font-mono text-sm text-[#a0a0a0]">:{{ port }}</span>
      </div>
      <span class="text-sm text-[#6b7280]">{{ session?.shell ?? '' }}</span>
    </div>

    <!-- Terminal Preview (CSS cover style) -->
    <div class="preview-container">
      <div class="terminal-cover">
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-card {
  width: 50vw;
  height: 50vh;
}

.preview-container {
  position: absolute;
  inset: 0;
}

.terminal-cover {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(var(--cover-scale, 1));
  width: 100%;
  height: 100%;
  transform-origin: center center;
}

/* Scale terminal content to cover the card */
.terminal-cover :deep(.xterm) {
  width: 100% !important;
  height: 100% !important;
}

.terminal-cover :deep(.xterm-viewport) {
  overflow: hidden !important;
}
</style>
```

**Alternative simpler approach** — just scale up and let overflow hide:

```vue
<!-- Terminal Preview (scaled to cover) -->
<div class="preview-container">
  <div class="terminal-wrapper">
    <slot></slot>
  </div>
</div>

<style scoped>
.session-card {
  width: 50vw;
  height: 50vh;
}

.preview-container {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.terminal-wrapper {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(2);
  width: 100%;
  height: 100%;
}
</style>
```

---

### 3. `manager_web_ui/src/views/HomeView.vue`

**Change:** Update grid to 2 columns max.

```vue
<!-- Before -->
<div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

<!-- After: 2x2 grid, then scroll -->
<div v-else class="grid grid-cols-2 gap-0">
```

No gap — cards are exactly 50vw/50vh, they'll tile perfectly. Remove padding from container too.

---

## Summary

| File | Change |
|------|--------|
| `TerminalViewport.vue` | Skip ResizeObserver + fit() when `interactive=false` |
| `SessionCard.vue` | 50vw×50vh size, CSS cover scaling for preview |
| `HomeView.vue` | 2-column grid, no gaps, full-height scroll |

---

## Checklist

- [x] Update `TerminalViewport.vue` — Skip ResizeObserver when `interactive=false`
- [x] Update `SessionCard.vue` — 50vw×50vh size with CSS cover scaling
- [x] Update `HomeView.vue` — 2-column grid, no gaps

---

## Testing

1. Open manager UI with multiple sessions
2. Check home page — cards are 2×2, scroll if >4 sessions
3. Terminal previews show content at terminal's actual size (no resize)
4. Click into a session — `fit()` runs, PTY resizes to full screen
5. Go back to home — PTY stays at full-screen size, preview shows cropped view
6. Resize browser on home — no PTY resize
7. Resize browser on session view — PTY resizes correctly
