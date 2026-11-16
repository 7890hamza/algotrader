<template>
  <div v-if="cells.length" class="seiz-strip" data-testid="seiz-dashboard">
    <svg :viewBox="`0 0 ${W} ${H}`" :width="W" :height="H" role="img" aria-label="SEIZ higher timeframe candles">
      <g v-for="(row, ri) in rowsOf" :key="ri">
        <text :x="4" :y="ri * ROW + 11" class="seiz-row-name">{{ ri ? 'Swing' : 'Intraday' }}</text>
        <g
          v-for="(cell, i) in row"
          :key="cell.key"
          class="seiz-candle"
          :class="{ 'seiz-candle--zone': cell.key === zoneTf }"
          @pointerenter="hovered = cell.key"
          @pointerleave="hovered = null"
        >
          <rect :x="x(i) - 6" :y="boxTop(ri)" :width="CW + 12" :height="BOX" rx="3" class="seiz-box" />
          <rect :x="x(i) - 7" :y="ri * ROW + 14" :width="CW + 14" :height="ROW - 16" fill="transparent" />
          <line :x1="mid(i)" :x2="mid(i)" :y1="y(ri, Math.min(cell.h ?? 0, 1))" :y2="y(ri, Math.max(cell.l ?? 0, 0))" class="seiz-wick" />
          <line
            v-if="(cell.h ?? 0) > 1"
            :x1="mid(i)"
:x2="mid(i)"
:y1="y(ri, cell.h ?? 1)"
:y2="y(ri, 1)"
            stroke="#C2475B"
stroke-width="3"
stroke-linecap="round"
:stroke-opacity="seizShade(cell.hi)"
          />
          <line
            v-if="(cell.l ?? 1) < 0"
            :x1="mid(i)"
:x2="mid(i)"
:y1="y(ri, 0)"
:y2="y(ri, cell.l ?? 0)"
            stroke="#1C9D7C"
stroke-width="3"
stroke-linecap="round"
:stroke-opacity="seizShade(cell.lo)"
          />
          <rect
            :x="x(i)"
:y="y(ri, Math.max(cell.o ?? 0, cell.c ?? 0))"
:width="CW"
            :height="Math.max(2, Math.abs((cell.o ?? 0) - (cell.c ?? 0)) * BOX)"
rx="1.5"
            :class="(cell.c ?? 0) >= (cell.o ?? 0) ? 'seiz-body-up' : 'seiz-body-down'"
          />
          <circle v-if="(cell.hi ?? 0) >= 185" :cx="mid(i)" :cy="y(ri, cell.h ?? 1) - 7" r="3" fill="#C2475B" />
          <circle v-if="(cell.lo ?? 0) >= 185" :cx="mid(i)" :cy="y(ri, cell.l ?? 0) + 7" r="3" fill="#1C9D7C" />
          <text :x="mid(i)" :y="ri * ROW + ROW - 4" text-anchor="middle" class="seiz-tf">{{ cell.label }}</text>
        </g>
      </g>
    </svg>
    <div class="seiz-note">{{ note }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { useIndicatorsStore } from "@/stores/indicatorsStore";
import type { IndicatorDataPoint } from "@/types/contracts";
import { dashCell, readSeizGuide, seizPairing, seizShade, type SeizStripCell } from "@/utils/chart/seiz";

defineOptions({ name: "SeizDashboard" });

// Strip geometry: two rows of eight candles; each candle is drawn in its last candle's range
// (the shaded box), so every timeframe reads the same way. Breakouts are capped just under half a box.
const CW = 10;
const GAP = 26;
const BOX = 44;
const PAD = 28;
const ROW = 14 + PAD + BOX + PAD + 16;
const W = 8 * GAP + 6;
const H = 2 * ROW;
const x = (i: number): number => 10 + i * GAP;
const mid = (i: number): number => x(i) + CW / 2;
const boxTop = (ri: number): number => ri * ROW + 14 + PAD;
const y = (ri: number, v: number): number => boxTop(ri) + BOX - Math.max(-0.45, Math.min(1.45, v)) * BOX;

const indicatorsStore = useIndicatorsStore();
const indicator = computed(() => indicatorsStore.all.find((item) => readSeizGuide(item.info.guide)) ?? null);
const hovered = ref<string | null>(null);

const param = (key: string): string => {
  const p = indicator.value?.parameters?.[key] as { value?: unknown; default?: unknown } | undefined;
  return String(p?.value ?? p?.default ?? "");
};
const zoneTf = computed(() => param("zone_tf") || "1h");

const num = (point: IndicatorDataPoint | null | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const cells = computed<SeizStripCell[]>(() => {
  const item = indicator.value;
  const guide = item ? readSeizGuide(item.info.guide) : null;
  if (!item || !guide || param("dashboard") === "off") return [];
  void item.dataVersion;
  const last = item.lastLivePoint ?? item.data[item.data.length - 1] ?? null;
  return guide.timeframes
    .map((tf) => ({
      key: tf.key,
      label: tf.label,
      hi: num(last, `d_${tf.key}_hi`),
      lo: num(last, `d_${tf.key}_lo`),
      pg: num(last, `d_${tf.key}_pg`),
      o: num(last, `d_${tf.key}_o`),
      h: num(last, `d_${tf.key}_h`),
      l: num(last, `d_${tf.key}_l`),
      c: num(last, `d_${tf.key}_c`),
    }))
    .filter((c) => c.o !== null && c.h !== null && c.l !== null);
});

const rowsOf = computed(() => [cells.value.slice(0, 8), cells.value.slice(8, 16)]);

const note = computed(() => {
  const cell = cells.value.find((c) => c.key === hovered.value);
  if (cell) {
    const side = (code: number | null): string => dashCell(code) || "–";
    return `${cell.label}: high ${side(cell.hi)} · low ${side(cell.lo)} · ${Math.round(cell.pg ?? 0)}% done`;
  }
  return seizPairing(cells.value) ?? "Every timeframe inside its normal range";
});
</script>

<style scoped>
.seiz-strip {
  position: absolute;
  top: 44px;
  right: 72px;
  z-index: 5;
  width: 230px;
  padding: 6px 6px 8px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px;
  background: rgba(13, 16, 23, 0.9);
  color: #d1d4dc;
}
svg { display: block; overflow: visible; }
.seiz-row-name { fill: #6e7681; font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; }
.seiz-box { fill: rgba(255, 255, 255, 0.045); }
.seiz-candle--zone .seiz-box { fill: rgba(255, 255, 255, 0.1); }
.seiz-candle:hover .seiz-box { fill: rgba(255, 255, 255, 0.14); }
.seiz-wick { stroke: #8a919c; stroke-width: 1.5; }
.seiz-body-up { fill: #e6e9ee; }
.seiz-body-down { fill: #5d6470; }
.seiz-tf { fill: #8a919c; font-size: 10.5px; font-weight: 600; }
.seiz-note { margin-top: 4px; padding: 0 4px; font-size: 11px; line-height: 1.35; color: #aab1bc; min-height: 2.7em; }
</style>
