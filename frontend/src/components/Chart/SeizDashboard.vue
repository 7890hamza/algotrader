<template>
  <div v-if="rows.length" class="seiz-dash" data-testid="seiz-dashboard">
    <div class="seiz-head">
      <span>TF</span><span>High</span><span>Low</span><span>Progress</span>
    </div>
    <div
      v-for="row in rows"
      :key="row.key"
      class="seiz-row"
      :class="{ 'seiz-row--zone': row.key === zoneTf }"
    >
      <span class="seiz-tf">{{ row.label }}</span>
      <span class="seiz-cell" :class="row.hiClass">{{ row.hi }}</span>
      <span class="seiz-cell" :class="row.loClass">{{ row.lo }}</span>
      <span class="seiz-pg"><i :style="{ width: `${row.pg}%` }" />{{ row.pg }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { useIndicatorsStore } from "@/stores/indicatorsStore";
import type { IndicatorDataPoint } from "@/types/contracts";
import { dashCell, readSeizGuide } from "@/utils/chart/seiz";

defineOptions({ name: "SeizDashboard" });

const indicatorsStore = useIndicatorsStore();
const indicator = computed(() => indicatorsStore.all.find((item) => readSeizGuide(item.info.guide)) ?? null);

const param = (key: string): string => {
  const p = indicator.value?.parameters?.[key] as { value?: unknown; default?: unknown } | undefined;
  return String(p?.value ?? p?.default ?? "");
};
const zoneTf = computed(() => param("zone_tf") || "1h");

const num = (point: IndicatorDataPoint | null | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

function cls(code: number | null): string {
  if (code === null || code === 0) return "seiz-none";
  const ext = code >= 100;
  const p = ext ? code - 100 : code;
  return `seiz-${ext ? "ext" : "int"} seiz-p${p}`;
}

const rows = computed(() => {
  const item = indicator.value;
  const guide = item ? readSeizGuide(item.info.guide) : null;
  if (!item || !guide || param("dashboard") === "off") return [];
  void item.dataVersion;
  const last = item.lastLivePoint ?? item.data[item.data.length - 1] ?? null;
  return guide.timeframes
    .map((tf) => {
      const hi = num(last, `d_${tf.key}_hi`);
      const lo = num(last, `d_${tf.key}_lo`);
      const pg = num(last, `d_${tf.key}_pg`);
      return { key: tf.key, label: tf.label, hi: dashCell(hi), lo: dashCell(lo), hiClass: cls(hi), loClass: cls(lo), pg: Math.round(pg ?? 0), ok: pg !== null };
    })
    .filter((r) => r.ok);
});
</script>

<style scoped>
.seiz-dash {
  position: absolute;
  top: 44px;
  right: 72px;
  z-index: 5;
  min-width: 236px;
  padding: 6px 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(13, 16, 23, 0.92);
  color: #d1d4dc;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  pointer-events: none;
}
.seiz-head, .seiz-row { display: grid; grid-template-columns: 34px 62px 62px 1fr; align-items: center; gap: 6px; padding: 2px 4px; }
.seiz-head { color: #6e7681; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 4px; margin-bottom: 2px; }
.seiz-row--zone { background: rgba(255, 255, 255, 0.06); border-radius: 4px; }
.seiz-tf { color: #8a919c; font-weight: 600; }
.seiz-cell { border-radius: 3px; padding: 1px 5px; text-align: center; }
.seiz-none { color: #4d5562; }
.seiz-int { color: #c9d1d9; background: rgba(47, 95, 150, 0.22); }
.seiz-ext { color: #f0f3f6; background: rgba(194, 71, 91, 0.22); }
.seiz-p85 { background: rgba(194, 71, 91, 0.42); }
.seiz-int.seiz-p85 { background: rgba(47, 95, 150, 0.42); }
.seiz-p99 { background: rgba(194, 71, 91, 0.65); font-weight: 700; }
.seiz-int.seiz-p99 { background: rgba(47, 95, 150, 0.65); }
.seiz-pg { position: relative; color: #8a919c; text-align: right; padding-right: 2px; }
.seiz-pg i { position: absolute; left: 0; top: 50%; height: 3px; margin-top: -1.5px; max-width: calc(100% - 36px); background: rgba(28, 157, 124, 0.7); border-radius: 2px; }
</style>
