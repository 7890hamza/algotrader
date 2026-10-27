<template>
  <div v-if="rows.length" class="tbr-card" data-testid="tbr-card">
    <div class="tbr-head">
      <span>Open fade ±0.25</span>
      <span class="tbr-head-note">came back</span>
    </div>
    <div
      v-for="row in rows"
      :key="row.key"
      class="tbr-row"
      :class="{ 'tbr-row--active': row.active }"
    >
      <span class="tbr-chip" :style="{ background: row.color }">{{ row.label }}</span>
      <span class="tbr-pct">{{ row.cameBack.toFixed(0) }}%</span>
      <span class="tbr-state" :class="`tbr-state--${row.state}`">{{ stateText(row.state) }}</span>
    </div>
    <div class="tbr-foot">{{ source }} · first touch back to the open</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { useIndicatorsStore } from "@/stores/indicatorsStore";
import type { IndicatorDataPoint, JsonObject } from "@/types/contracts";

defineOptions({ name: "TbrStatsOverlay" });

interface TbrSession { key: string; label: string; color: string; window: string; cameBack: number; touched: number }
type RowState = "idle" | "waiting" | "touched" | "back";

const indicatorsStore = useIndicatorsStore();

const indicator = computed(() =>
  indicatorsStore.all.find((item) => (item.info.guide as JsonObject | undefined)?.kind === "tbr") ?? null,
);

const source = computed(() => {
  const value = indicator.value?.info.guide?.source;
  return typeof value === "string" ? value : "Past data";
});

const num = (point: IndicatorDataPoint | null | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const rows = computed(() => {
  const item = indicator.value;
  if (!item) return [];
  const sessions = (item.info.guide?.sessions ?? []) as unknown as TbrSession[];
  const param = item.parameters?.sessions as { value?: unknown; default?: unknown } | undefined;
  const chosen = String(param?.value ?? param?.default ?? "")
    .toLowerCase()
    .split(/[,;]/)
    .map((s) => s.trim())
    .filter(Boolean);
  void item.dataVersion;
  const last = item.lastLivePoint ?? item.data[item.data.length - 1] ?? null;
  return sessions
    .filter((s) => chosen.length === 0 || chosen.includes(s.key))
    .map((s) => {
      const live = num(last, `${s.key}_open`) !== null;
      let state: RowState = "idle";
      if (live) {
        state = num(last, `${s.key}_revert_at`) !== null ? "back"
          : num(last, `${s.key}_stretch_near`) !== null ? "touched" : "waiting";
      }
      return { ...s, active: live, state };
    });
});

function stateText(state: RowState): string {
  if (state === "back") return "back at open ✓";
  if (state === "touched") return "touched, watching";
  if (state === "waiting") return "no touch yet";
  return "";
}
</script>

<style scoped>
.tbr-card {
  position: absolute;
  right: 72px;
  bottom: 40px;
  z-index: 5;
  min-width: 230px;
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(19, 23, 34, 0.92);
  color: #d1d4dc;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  pointer-events: none;
}

.tbr-head { display: flex; justify-content: space-between; margin-bottom: 6px; font-weight: 600; }
.tbr-head-note { color: #8a919c; font-weight: 400; }
.tbr-row { display: grid; grid-template-columns: 64px 40px 1fr; align-items: center; gap: 8px; padding: 3px 4px; border-radius: 4px; opacity: 0.6; }
.tbr-row--active { opacity: 1; background: rgba(255, 255, 255, 0.05); }
.tbr-chip { padding: 1px 6px; border-radius: 3px; color: #0f1218; font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 11px; font-weight: 700; text-align: center; }
.tbr-pct { text-align: right; font-weight: 600; }
.tbr-state { color: #8a919c; font-size: 11px; }
.tbr-state--back { color: #f2d16b; }
.tbr-state--touched { color: #e6e6e6; }
.tbr-foot { margin-top: 6px; color: #5d6570; font-size: 11px; }
</style>
