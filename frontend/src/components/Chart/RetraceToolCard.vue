<template>
  <div class="rtc" :class="model.up ? 'rtc--up' : 'rtc--down'" data-testid="retrace-tool-card">
    <div class="rtc-row rtc-head">
      <span class="rtc-title">Retrace · {{ model.up ? 'up leg' : 'down leg' }}</span>
      <button class="rtc-btn rtc-close" type="button" aria-label="Remove this retrace" @click="$emit('remove')">×</button>
    </div>
    <div class="rtc-row rtc-dim">
      {{ fmt(drawing.a.price) }} → {{ fmt(drawing.b.price) }} · {{ fmt(model.range) }} pts
    </div>
    <div class="rtc-row">
      <span>Zone</span>
      <input :value="drawing.from" type="number" step="1" aria-label="Zone start percent" data-testid="retrace-from" @change="onPct('from', $event)">
      <span class="rtc-dim">to</span>
      <input :value="drawing.to" type="number" step="1" aria-label="Zone end percent" data-testid="retrace-to" @change="onPct('to', $event)">
      <span class="rtc-dim">%</span>
    </div>
    <div class="rtc-row rtc-zone">
      {{ fmt(model.zoneLow) }} – {{ fmt(model.zoneHigh) }}
    </div>
    <div class="rtc-row">
      <span>Lines</span>
      <input
        class="rtc-lines"
        :value="drawing.lines.join(', ')"
        type="text"
        placeholder="50, 100"
        aria-label="Extra lines in percent"
        data-testid="retrace-lines"
        @change="onLines"
      >
    </div>
    <div class="rtc-row rtc-dim rtc-help">
      Percent back from the second anchor toward the first. Over 100 or below 0 goes past an anchor.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

import { buildRetraceModel, type RetraceDrawing } from '@/utils/chart/retraceTool';

defineOptions({ name: 'RetraceToolCard' });

const props = defineProps<{ drawing: RetraceDrawing }>();
const emit = defineEmits<{
  remove: [];
  update: [patch: { from?: number; to?: number; lines?: string }];
}>();

const model = computed(() => buildRetraceModel(props.drawing));
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function onPct(key: 'from' | 'to', event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  if (Number.isFinite(value)) emit('update', { [key]: value });
}

function onLines(event: Event): void {
  emit('update', { lines: (event.target as HTMLInputElement).value });
}
</script>

<style scoped>
.rtc {
  position: absolute;
  bottom: 44px;
  left: 270px;
  z-index: 7;
  width: 230px;
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid #2fb67c;
  background: rgba(19, 23, 34, 0.92);
  color: #d1d4dc;
  font-size: 12px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.rtc--down { border-left-color: #e5534b; }
.rtc-row { display: flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
.rtc-row > span:first-child { min-width: 36px; color: #8a919c; }
.rtc-head { justify-content: space-between; }
.rtc-title { font-weight: 600; color: #e6e6e6 !important; }
.rtc-btn { background: transparent; border: 0; color: #d1d4dc; cursor: pointer; font-size: 16px; line-height: 1; }
.rtc-dim { color: #8a919c; font-size: 11px; }
.rtc-zone { font-weight: 600; color: #2fb67c; padding-left: 42px; }
.rtc--down .rtc-zone { color: #e5534b; }
.rtc input { width: 52px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 4px; color: #e6e6e6; padding: 2px 4px; font: inherit; }
.rtc input.rtc-lines { width: 130px; }
.rtc-help { line-height: 1.35; }
</style>
