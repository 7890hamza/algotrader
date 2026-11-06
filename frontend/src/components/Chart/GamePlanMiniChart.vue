<template>
  <div class="gpm" data-testid="game-plan-mini-chart">
    <div class="gpm-head">
      <span class="gpm-title">{{ symbol }} · {{ stepLabel }} · {{ plan.label }}</span>
      <span v-if="readout" class="gpm-readout">{{ readout }}</span>
      <button v-else-if="moved" class="gpm-reset" type="button" title="Back to the default view" @click="resetView">Reset view</button>
    </div>
    <div ref="host" class="gpm-chart" />
  </div>
</template>

<script setup lang="ts">
import {
  createChart,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type AutoscaleInfo,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import type { Board, DayPlan, PlanLevel } from '@/utils/chart/gamePlan';
import { GamePlanMiniPrimitive, miniName, type MiniOpen } from '@/utils/chart/gamePlanMiniPrimitive';

defineOptions({ name: 'GamePlanMiniChart' });

const props = defineProps<{ plan: DayPlan; board: Board; t: number; price: number }>();

const host = ref<HTMLDivElement | null>(null);
const readout = ref('');
const moved = ref(false);
const symbol = computed(() => props.plan.symbol || 'ES');
// A long window draws from 15-minute closes (a cleaner line); a short one from 5-minute closes.
const step = computed(() => {
  const [a, b] = defaultWindow(props.plan, props.t);
  return b - a > 6 * HOUR ? 15 * 60_000 : 5 * 60_000;
});
const stepLabel = computed(() => `${step.value / 60_000}m`);

const HOUR = 3_600_000;
const TZ = 'America/Los_Angeles';
const COLORS = { up: '#2fb67c', down: '#e5534b', gold: '#e9c46a', axis: '#8a919c', tagText: '#0d1017' };
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const clock = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hour: 'numeric', minute: '2-digit' });
const hourOnly = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hour: 'numeric' });

let chart: IChartApi | null = null;
let series: ISeriesApi<'Line'> | null = null;
let primitive: GamePlanMiniPrimitive | null = null;
let liveLine: IPriceLine | null = null;
let tagLines: IPriceLine[] = [];
let shiftMs = 0;
let dayKey = '';
let lastTime = 0;
let autoView = true;
let settingView = false;
let lastSet: { from: number; to: number } | null = null;
let lastInput = 0;
const markInput = (): void => { lastInput = Date.now(); };
let shown: { open: MiniOpen[]; hits: PlanLevel[] } = { open: [], hits: [] };

/** Pacific time offset at a moment, so the chart's clock reads in Pacific time. */
function ptOffset(ms: number): number {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: TZ, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })
    .formatToParts(new Date(ms))
    .reduce<Record<string, number>>((a, p) => (p.type === 'literal' ? a : { ...a, [p.type]: Number(p.value) }), {});
  return Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute) - Math.floor(ms / 60_000) * 60_000;
}
const toTime = (ms: number): UTCTimestamp => Math.floor((ms + shiftMs) / 1000) as UTCTimestamp;

/** The window the chart opens on: from RTH on, the last ~13 h to a little past the close;
 * before RTH, the session so far with a couple of hours of room. */
function defaultWindow(plan: DayPlan, t: number): [number, number] {
  const a = Math.max(plan.start, Math.min(t, plan.ctx.rth1) - 13 * HOUR);
  const b = t >= plan.ctx.rth0
    ? Math.min(plan.end, Math.max(t, plan.ctx.rth1) + 40 * 60_000)
    : Math.min(plan.ctx.rth1 + 40 * 60_000, Math.max(t + 2 * HOUR, a + 4 * HOUR));
  return [a, b];
}

function pathData(): LineData<Time>[] {
  const out: LineData<Time>[] = [];
  for (const r of props.plan.path ?? []) {
    const time = toTime(Math.floor(r[0] / step.value) * step.value);
    const last = out[out.length - 1];
    if (last && last.time === time) last.value = r[3];
    else out.push({ time, value: r[3] });
  }
  return out;
}

/** The two nearest open targets above, one or two below and the last two hits; none so far
 * away they would flatten the line (the list above the chart has them all). */
function pickLevels(): void {
  const [a] = defaultWindow(props.plan, props.t);
  let hi = props.price;
  let lo = props.price;
  for (const r of props.plan.path ?? []) if (r[0] >= a) { hi = Math.max(hi, r[1]); lo = Math.min(lo, r[2]); }
  const reach = Math.max(hi - lo, 15) * 1.2;
  const near = (p: number): boolean => p <= hi + reach && p >= lo - reach;
  shown = {
    open: [...props.board.above.slice(-2), ...props.board.below.slice(0, 2)]
      .filter((r) => near(r.level.price))
      .map((r) => ({ level: r.level, odds: r.odds.value })),
    hits: props.board.done.filter((r) => r.level.hitAt !== null && r.level.hitAt >= a && near(r.level.price)).slice(0, 2).map((r) => r.level),
  };
}

function renderLevels(): void {
  if (!series || !primitive) return;
  pickLevels();
  primitive.set({ plan: props.plan, t: props.t, open: shown.open, hits: shown.hits, shiftMs });
  for (const l of tagLines) series.removePriceLine(l);
  tagLines = shown.open.map(({ level }) =>
    series!.createPriceLine({ price: level.price, color: level.color, lineVisible: false, axisLabelVisible: true, axisLabelColor: level.color, axisLabelTextColor: COLORS.tagText, title: '' }),
  );
  const color = props.plan.ctx.dayOpen !== undefined && props.price < props.plan.ctx.dayOpen ? COLORS.down : COLORS.up;
  series.applyOptions({ color });
}

function applyView(): void {
  if (!chart || !series) return;
  const data = series.data();
  if (!data.length) return;
  const [a, b] = defaultWindow(props.plan, props.t);
  const first = data.findIndex((d) => Number(d.time) >= toTime(a));
  const lastIdx = data.length - 1;
  const future = Math.max(2, Math.round((b - Math.max(props.t, props.plan.start)) / step.value));
  lastSet = { from: Math.max(0, first), to: lastIdx + future };
  settingView = true;
  chart.timeScale().setVisibleLogicalRange(lastSet);
  settingView = false;
  autoView = true;
  moved.value = false;
}

function resetView(): void {
  applyView();
}

function loadData(): void {
  if (!series) return;
  const data = pathData();
  series.setData(data);
  lastTime = data.length ? Number(data[data.length - 1].time) : 0;
  liveTick();
  renderLevels();
  if (props.plan.key !== dayKey || autoView) {
    dayKey = props.plan.key;
    applyView();
  }
}

/** Moves the line's last point and the gold tag with the live price. */
function liveTick(): void {
  if (!series || !Number.isFinite(props.price)) return;
  const time = toTime(Math.floor(props.t / step.value) * step.value);
  if (Number(time) >= lastTime) {
    series.update({ time, value: props.price });
    lastTime = Number(time);
  }
  if (liveLine) liveLine.applyOptions({ price: props.price });
  else liveLine = series.createPriceLine({ price: props.price, color: COLORS.gold, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, axisLabelColor: COLORS.gold, axisLabelTextColor: COLORS.tagText, title: '' });
}

onMounted(() => {
  if (!host.value) return;
  shiftMs = ptOffset(props.plan.start);
  chart = createChart(host.value, {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: COLORS.axis, fontSize: 11, attributionLogo: false },
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    // No price numbers: only the colored tags, like the mockup.
    rightPriceScale: { borderVisible: false, textColor: 'transparent', scaleMargins: { top: 0.1, bottom: 0.14 } },
    timeScale: {
      visible: false,
      borderVisible: false,
      timeVisible: true,
      secondsVisible: false,
      shiftVisibleRangeOnNewBar: false,
      rightOffset: 0,
      tickMarkFormatter: (time: Time) => {
        const d = new Date(Number(time) * 1000);
        return d.getUTCMinutes() ? clock.format(d).replace(' AM', '').replace(' PM', '') : hourOnly.format(d);
      },
    },
    localization: { locale: 'en-US', timeFormatter: (time: Time) => clock.format(new Date(Number(time) * 1000)) },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: 'rgba(215, 219, 227, 0.3)', style: LineStyle.Dashed, labelBackgroundColor: '#2a2f3d' },
      horzLine: { color: 'rgba(215, 219, 227, 0.3)', style: LineStyle.Dashed, labelBackgroundColor: '#2a2f3d' },
    },
  });
  series = chart.addSeries(LineSeries, {
    color: COLORS.down,
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerRadius: 3,
    priceFormat: { type: 'price', precision: 2, minMove: 0.25 },
    // keep the shown targets in view
    autoscaleInfoProvider: (base: () => AutoscaleInfo | null) => {
      const res = base();
      if (!res?.priceRange) return res;
      for (const p of [...shown.open.map((o) => o.level.price), ...shown.hits.map((h) => h.price), props.price]) {
        res.priceRange.minValue = Math.min(res.priceRange.minValue, p);
        res.priceRange.maxValue = Math.max(res.priceRange.maxValue, p);
      }
      return res;
    },
  });
  host.value.addEventListener('pointerdown', markInput);
  host.value.addEventListener('wheel', markInput, { passive: true });
  primitive = new GamePlanMiniPrimitive();
  series.attachPrimitive(primitive);
  chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (settingView || !r || !lastSet) return;
    if (Date.now() - lastInput > 1500) return; // a resize or new data, not you dragging or zooming
    if (Math.abs(r.from - lastSet.from) < 0.5 && Math.abs(r.to - lastSet.to) < 0.5) return;
    autoView = false;
    moved.value = true;
  });
  chart.subscribeCrosshairMove((param) => {
    if (!param.point || !param.time || !series) {
      readout.value = '';
      return;
    }
    const y = param.point.y;
    const onLine = [...shown.open.map((o) => o.level), ...shown.hits]
      .map((l) => ({ l, dy: Math.abs((series!.priceToCoordinate(l.price) ?? -999) - y) }))
      .filter((r) => r.dy <= 5)
      .sort((a, b) => a.dy - b.dy)[0];
    if (onLine) {
      const l = onLine.l;
      const odds = shown.open.find((o) => o.level.id === l.id)?.odds;
      readout.value = l.hitAt !== null && l.hitAt <= props.t
        ? `✓ ${miniName(l.label)} hit ${clock.format(new Date(l.hitAt + shiftMs))}`
        : `${miniName(l.label)}${odds != null ? ` · ${odds}%` : ''} · ${fmt(l.price)}`;
      return;
    }
    const d = param.seriesData.get(series) as LineData<Time> | undefined;
    readout.value = d ? `${clock.format(new Date(Number(param.time) * 1000))} · ${fmt(d.value)}` : '';
  });
  loadData();
});

onBeforeUnmount(() => {
  host.value?.removeEventListener('pointerdown', markInput);
  host.value?.removeEventListener('wheel', markInput);
  chart?.remove();
  chart = null;
  series = null;
  primitive = null;
  liveLine = null;
  tagLines = [];
});

watch(() => props.plan, () => {
  if (props.plan.key !== dayKey) shiftMs = ptOffset(props.plan.start);
  loadData();
});
watch(step, () => loadData());
watch(() => [props.t, props.price], () => {
  liveTick();
  renderLevels();
});
</script>

<style scoped>
.gpm {
  flex: 1 1 auto;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #131722;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 8px;
  padding: 10px 4px 4px 10px;
}
.gpm-head { display: flex; justify-content: space-between; align-items: center; gap: 6px; color: #8a919c; font-size: 11px; min-height: 16px; padding-right: 6px; }
.gpm-title { white-space: nowrap; }
.gpm-readout { color: #d7dbe3; font-family: ui-monospace, Menlo, monospace; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.gpm-reset { background: transparent; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 4px; color: #8a919c; font-size: 10.5px; padding: 1px 6px; cursor: pointer; }
.gpm-reset:hover { color: #d7dbe3; }
.gpm-chart { flex: 1 1 auto; min-height: 290px; position: relative; padding-bottom: 0; }
</style>
