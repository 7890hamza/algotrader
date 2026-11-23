<template>
  <div class="dt" :class="{ 'dt--open': open }" data-testid="drawing-toolbar" @pointerdown.stop @wheel.stop>
    <button type="button" class="dt__btn dt__toggle" :title="open ? 'Hide drawing tools' : 'Drawing tools'" @click="setOpen(!open)">
      <svg viewBox="0 0 24 24"><path :d="open ? 'M15 6l-6 6 6 6' : 'M4 20l4-1 11-11-3-3L5 16l-1 4z M14 6l3 3'" /></svg>
    </button>
    <template v-if="open">
      <button type="button" class="dt__btn" :class="{ 'dt__btn--on': state.tool === null }" title="Cursor (Esc)" @click="$emit('tool', null)">
        <svg viewBox="0 0 24 24"><path d="M6 3l12 9-6 1 3 7-2 1-3-7-4 4z" /></svg>
      </button>
      <button
        v-for="t in TOOLS"
        :key="t.kind"
        type="button"
        class="dt__btn"
        :class="{ 'dt__btn--on': state.tool === t.kind }"
        :title="t.key ? `${t.label} (${t.key})` : t.label"
        :data-testid="`draw-${t.kind}`"
        @click="$emit('tool', state.tool === t.kind ? null : t.kind)"
      >
        <svg viewBox="0 0 24 24"><path :d="ICONS[t.kind]" /></svg>
      </button>
      <span class="dt__sep" />
      <button type="button" class="dt__btn" :class="{ 'dt__btn--on': state.magnet }" title="Magnet: snap to candle open / high / low / close" @click="$emit('magnet')">
        <svg viewBox="0 0 24 24"><path d="M6 4v8a6 6 0 0012 0V4h-4v8a2 2 0 01-4 0V4z M6 7h4 M14 7h4" /></svg>
      </button>
      <button type="button" class="dt__btn" :class="{ 'dt__btn--on': state.hidden }" :title="state.hidden ? 'Show drawings' : 'Hide drawings'" @click="$emit('hide')">
        <svg viewBox="0 0 24 24"><path :d="state.hidden ? 'M3 3l18 18 M10.6 6.1A10 10 0 0122 12a13 13 0 01-3 3.6 M6.6 6.6A13 13 0 002 12s4 7 10 7a9 9 0 004-1' : 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9a3 3 0 110 6 3 3 0 010-6z'" /></svg>
      </button>
      <button
        type="button"
        class="dt__btn"
        :class="{ 'dt__btn--warn': sure }"
        :disabled="!state.count"
        :title="sure ? 'Click again to delete all drawings on this symbol' : 'Delete all drawings'"
        @click="clearAll"
      >
        <svg viewBox="0 0 24 24"><path d="M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13" /></svg>
      </button>
    </template>
    <div v-if="state.selected" class="dt__sel" data-testid="drawing-selected">
      <button
        v-for="c in COLORS"
        :key="c"
        type="button"
        class="dt__swatch"
        :class="{ 'dt__swatch--on': state.selected.color === c }"
        :style="{ background: c }"
        :title="`Color ${c}`"
        @click="$emit('style', { color: c })"
      />
      <button type="button" class="dt__btn" :class="{ 'dt__btn--on': state.selected.dashed }" title="Dashed line" @click="$emit('style', { dashed: !state.selected.dashed })">
        <svg viewBox="0 0 24 24"><path d="M3 12h4 M10 12h4 M17 12h4" /></svg>
      </button>
      <button type="button" class="dt__btn dt__btn--del" title="Delete (Del)" @click="$emit('remove')">
        <svg viewBox="0 0 24 24"><path d="M6 6l12 12 M18 6L6 18" /></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

import { COLORS, TOOLS, type DrawKind, type Drawing } from '@/utils/chart/drawings';
import { getStoredState, setStoredState } from '@/utils/localStorage';

defineOptions({ name: 'DrawingToolbar' });
defineProps<{ state: { tool: DrawKind | null; selected: Drawing | null; count: number; hidden: boolean; magnet: boolean } }>();
const emit = defineEmits<{
  tool: [kind: DrawKind | null];
  style: [patch: { color?: string; dashed?: boolean }];
  remove: [];
  'remove-all': [];
  hide: [];
  magnet: [];
}>();

const OPEN_KEY = 'algotrader_drawings_toolbar_open';
const open = ref<boolean>(getStoredState<boolean>(OPEN_KEY) ?? true);
function setOpen(v: boolean): void {
  open.value = v;
  setStoredState(OPEN_KEY, v);
  if (!v) emit('tool', null);
}
const sure = ref(false);
let sureTimer: ReturnType<typeof setTimeout> | null = null;
function clearAll(): void {
  if (!sure.value) {
    sure.value = true;
    if (sureTimer) clearTimeout(sureTimer);
    sureTimer = setTimeout(() => { sure.value = false; }, 3000);
    return;
  }
  sure.value = false;
  emit('remove-all');
}

const ICONS: Record<DrawKind, string> = {
  trend: 'M5 19L19 5 M5 19m-1.5 0a1.5 1.5 0 103 0 1.5 1.5 0 10-3 0 M19 5m-1.5 0a1.5 1.5 0 103 0 1.5 1.5 0 10-3 0',
  ray: 'M5 19L21 3 M5 19m-1.5 0a1.5 1.5 0 103 0 1.5 1.5 0 10-3 0 M13 11m-1.5 0a1.5 1.5 0 103 0 1.5 1.5 0 10-3 0',
  hline: 'M2 12h20',
  hray: 'M6 12h16 M6 12m-1.5 0a1.5 1.5 0 103 0 1.5 1.5 0 10-3 0',
  vline: 'M12 2v20',
  rect: 'M4 6h16v12H4z',
  text: 'M5 5h14 M12 5v14 M9 19h6',
};
</script>

<style scoped>
.dt {
  position: absolute; left: 6px; top: 96px; z-index: 6;
  display: flex; flex-direction: column; gap: 2px; padding: 3px;
  background: rgba(19, 23, 34, 0.55); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
  opacity: 0.55; transition: opacity 0.15s;
}
.dt:hover, .dt--open:focus-within { opacity: 1; }
.dt__btn {
  width: 28px; height: 28px; display: grid; place-items: center; padding: 0;
  border: 0; border-radius: 6px; background: transparent; color: #b8bfca; cursor: pointer;
}
.dt__btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.dt__btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
.dt__btn--on { background: rgba(76, 159, 254, 0.22); color: #8fc2ff; }
.dt__btn--warn { background: rgba(229, 83, 75, 0.3); color: #ffb3ad; }
.dt__btn--del:hover { color: #ff8a80; }
.dt__btn:disabled { opacity: 0.35; cursor: default; }
.dt__sep { height: 1px; margin: 3px 4px; background: rgba(255, 255, 255, 0.1); }
.dt__sel { display: flex; flex-direction: column; align-items: center; gap: 4px; margin-top: 4px; padding-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.1); }
.dt__swatch { width: 16px; height: 16px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0; }
.dt__swatch--on { border-color: #fff; }
</style>
