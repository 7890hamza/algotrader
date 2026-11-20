<template>
  <div class="setups-page" data-testid="setups-page">
    <header class="head">
      <div>
        <h1>Setups</h1>
        <p class="sub">
          The 7 indicator pairings from the 2026 backtest, on your MT5 data. Each trade: enter when both
          conditions line up, aim for {{ TARGET }} points, give it {{ STOP }}. Green = the {{ TARGET }} points it was
          after, red = the {{ STOP }}-point stop.
        </p>
      </div>
      <div class="controls">
        <label class="ctl">Market
          <select id="setups-symbol" v-model="symbol" @change="load">
            <option v-for="m in markets" :key="m.symbol + m.exchange" :value="m.symbol">{{ m.symbol }}</option>
          </select>
        </label>
        <label class="ctl">From
          <select id="setups-period" v-model="period" @change="load">
            <option value="ytd">Jan 1, 2026</option>
            <option value="90">Last 90 days</option>
            <option value="30">Last 30 days</option>
          </select>
        </label>
        <button class="btn" type="button" @click="load">Refresh</button>
      </div>
    </header>

    <p v-if="status" class="status" :class="{ err: failed }">{{ status }}</p>

    <div class="chips" role="group" aria-label="Show or hide setups">
      <button
        v-for="s in scores"
        :id="`setup-chip-${s.id}`"
        :key="s.id"
        type="button"
        class="chip"
        :aria-pressed="shown.has(s.id)"
        @click="toggle(s.id)"
      >
        <b><span class="tag" :class="SETUP_BY_ID[s.id].dir > 0 ? 'long' : 'short'">{{ s.id }} {{ SETUP_BY_ID[s.id].dir > 0 ? '▲' : '▼' }}</span>{{ SETUP_BY_ID[s.id].name }}</b>
        <span class="meta">{{ s.trades }} trades · hit {{ TARGET }} in {{ Math.round(s.hitRate * 100) }}% · {{ s.pts > 0 ? '+' : '' }}{{ s.pts }} pts</span>
      </button>
    </div>

    <div class="bar">
      <button class="btn" type="button" aria-label="Previous day" :disabled="dayIndex <= 0" @click="step(-1)">◀ Prev</button>
      <select id="setups-day" v-model="day" aria-label="Pick a day">
        <option v-for="d in [...days].reverse()" :key="d" :value="d">{{ dayLabel(d) }}</option>
      </select>
      <button class="btn" type="button" aria-label="Next day" :disabled="dayIndex >= days.length - 1" @click="step(1)">Next ▶</button>
      <span class="dayname">{{ day ? longDay(day) : '' }}</span>
      <span class="daysum">{{ daySummary }}</span>
      <span class="spacer" />
      <label class="inline"><input id="stacks-on" v-model="stacksOn" type="checkbox"> Stacked stats</label>
      <label class="inline">at least
        <select id="stacks-min" v-model.number="minCount"><option :value="2">2</option><option :value="3">3</option><option :value="4">4</option></select>
        stats within
        <select id="stacks-width" v-model.number="width"><option :value="2">2 pts</option><option :value="3">3 pts</option><option :value="5">5 pts</option><option :value="8">8 pts</option></select>
      </label>
    </div>

    <div class="stage">
      <div ref="chartEl" class="chart" />
      <div class="legend">{{ legend }}</div>
    </div>

    <div class="list">
      <div
        v-for="t in dayTrades"
        :key="t.id + t.entryMs"
        class="trade"
        :class="{ on: selected === t }"
        tabindex="0"
        @click="focusTrade(t)"
        @keydown.enter="focusTrade(t)"
      >
        <div class="top">
          <span class="name"><span class="tag" :class="t.dir > 0 ? 'long' : 'short'">{{ t.id }} {{ t.dir > 0 ? '▲ long' : '▼ short' }}</span>{{ SETUP_BY_ID[t.id].name }}</span>
          <span class="res" :class="t.pts > 0 ? 'win' : t.pts < 0 ? 'loss' : ''">{{ t.pts > 0 ? '+' : '' }}{{ t.pts }}</span>
        </div>
        <p>{{ clock(t.entryMs) }} entry at {{ t.entry.toFixed(2) }}, {{ howText(t) }} at {{ clock(t.exitMs) }}.</p>
        <p>{{ SETUP_BY_ID[t.id].why }}</p>
        <span v-if="t.levels.length" class="lv">{{ t.levels.map((l) => `${l.name} ${l.price.toFixed(2)}`).join(' · ') }}</span>
      </div>
    </div>
    <section v-if="stacksOn && (hitList.length || openList.length)" class="stacks">
      <h2>Stacked stats</h2>
      <div v-for="(z, i) in hitList" :key="'h' + i" class="stack">
        <b>{{ clock(z.from) }}{{ z.to > z.from ? `–${clock(z.to)}` : '' }} · {{ z.count }} stats hit at {{ z.lo.toFixed(2) }}{{ z.hi > z.lo ? `–${z.hi.toFixed(2)}` : '' }}</b>
        <p>{{ z.labels.join(' · ') }}</p>
        <p v-if="z.back !== null">
          Mean reversion: price came {{ z.approach > 0 ? 'down into' : 'up into' }} it, then came back
          <span class="win">{{ z.back > 0 ? '+' : '' }}{{ z.back.toFixed(2) }} pts</span> within an hour
          <template v-if="z.further">(it went <span class="loss">{{ z.further.toFixed(2) }} pts</span> further first)</template>.
        </p>
      </div>
      <div v-for="(z, i) in openList" :key="'o' + i" class="stack ahead">
        <b>{{ asOfText }}: {{ z.count }} stats stack at {{ z.lo.toFixed(2) }}{{ z.hi > z.lo ? `–${z.hi.toFixed(2)}` : '' }} · {{ z.away }} pts away</b>
        <p>{{ z.labels.join(' · ') }}</p>
      </div>
    </section>
    <p class="how">
      Hover the chart to see which stats stack ahead of price from that moment. Results include {{ COST }} points of costs; a trade still open after an hour closes at the market. Yellow lines are the
      two levels that made the setup fire. Odds from this year's data, not trade calls.
    </p>
  </div>
</template>

<script setup lang="ts">
import {
  CandlestickSeries, createChart, type IChartApi, type IPrimitivePaneRenderer, type IPrimitivePaneView,
  type ISeriesApi, type ISeriesPrimitive, type SeriesAttachedParameter, type Time, type UTCTimestamp,
} from 'lightweight-charts';
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';

import { fetchCandles } from '@/api/candleClient';
import { fetchGamePlan } from '@/api/gamePlanClient';
import { requestIndicator } from '@/api/indicatorClient';
import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useMarketsStore } from '@/stores/marketsStore';
import { createChartTimeFormatters } from '@/utils/chart/chartTimeZone';
import {
  cmeDayBounds, hitStacks, openStacks, scoreSetups, SETUP_BY_ID, SETUPS, type SetupId, type SetupTrade,
  type StatLevel, tradesFrom,
} from '@/utils/setups';

defineOptions({ name: 'SetupsView' });

const SETUPS_INDICATOR_ID = 19;
const TARGET = 10;
const STOP = 3;
const COST = 0.5;
const COLORS = { long: '#2fbf8f', short: '#e0566c', watch: '#e3ad42', fg: '#e8ebf0', muted: '#8b93a1' };

const marketsStore = useMarketsStore();
const currentMarket = useCurrentMarketStore();
const markets = computed(() => marketsStore.all.filter((m) => !m.exchange.toUpperCase().includes('HYPER')));
const symbol = ref<string>(currentMarket.symbol ?? 'ES');
const period = ref<'ytd' | '90' | '30'>('ytd');
const trades = shallowRef<SetupTrade[]>([]);
const status = ref('');
const failed = ref(false);
const shown = ref(new Set<SetupId>(SETUPS.map((s) => s.id)));
const day = ref<string>('');
const selected = shallowRef<SetupTrade | null>(null);
const legend = ref('5-min candles · New York time');

// Stacked stats (Game Plan levels that line up at one price)
const stacksOn = ref(true);
const minCount = ref(3);
const width = ref(3);
const stats = shallowRef<StatLevel[]>([]);
const candleData = shallowRef<{ time: number; high: number; low: number; close: number }[]>([]);
const asOf = ref<number | null>(null); // ms; null = the last candle
const hitList = computed(() => (stacksOn.value ? hitStacks(stats.value, candleData.value, width.value, minCount.value) : []));
const asOfMs = computed(() => asOf.value ?? ((candleData.value[candleData.value.length - 1]?.time ?? 0) * 1000));
const asOfPrice = computed(() => {
  const t = asOfMs.value / 1000;
  const c = [...candleData.value].reverse().find((x) => x.time <= t);
  return c?.close ?? 0;
});
const openList = computed(() => (stacksOn.value && candleData.value.length
  ? openStacks(stats.value, asOfMs.value, asOfPrice.value, width.value, minCount.value).slice(0, 4) : []));
const asOfText = computed(() => (asOf.value === null ? 'Ahead of price now' : `Ahead of price at ${clock(asOfMs.value)}`));

const visible = computed(() => trades.value.filter((t) => shown.value.has(t.id)));
const scores = computed(() => scoreSetups(trades.value));
const days = computed(() => [...new Set(visible.value.map((t) => t.day))].sort());
const dayIndex = computed(() => days.value.indexOf(day.value));
const dayTrades = computed(() => visible.value.filter((t) => t.day === day.value));
const daySummary = computed(() => {
  const ts = dayTrades.value;
  if (!ts.length) return '';
  const pts = ts.reduce((a, t) => a + t.pts, 0);
  return `${ts.length} trade${ts.length > 1 ? 's' : ''} · ${ts.filter((t) => t.how === 'target').length} hit ${TARGET} · ${pts > 0 ? '+' : ''}${pts.toFixed(2)} pts`;
});

const ny = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', ...opts });
const clockFmt = ny({ hour: 'numeric', minute: '2-digit' });
const clock = (ms: number): string => clockFmt.format(new Date(ms));
const dayLabel = (d: string): string => {
  const ts = visible.value.filter((t) => t.day === d);
  const pts = ts.reduce((a, t) => a + t.pts, 0);
  const name = new Date(`${d}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
  return `${name} · ${ts.length} trade${ts.length > 1 ? 's' : ''} · ${pts > 0 ? '+' : ''}${pts.toFixed(1)}`;
};
const longDay = (d: string): string => new Date(`${d}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' });
const howText = (t: SetupTrade): string => (t.how === 'target' ? `hit the ${TARGET}-point target` : t.how === 'stop' ? `stopped out (${STOP} points)` : 'closed after an hour');

function toggle(id: SetupId): void {
  const next = new Set(shown.value);
  if (next.has(id)) next.delete(id); else next.add(id);
  shown.value = next;
  if (!days.value.includes(day.value)) day.value = days.value[days.value.length - 1] ?? '';
}
function step(by: number): void {
  const d = days.value[dayIndex.value + by];
  if (d) day.value = d;
}

// ---- chart ----
const chartEl = ref<HTMLDivElement | null>(null);
let chart: IChartApi | null = null;
let series: ISeriesApi<'Candlestick'> | null = null;
let bars: { time: number }[] = [];
let drawn: SetupTrade[] = [];

const rgba = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

class TradesPrimitive implements ISeriesPrimitive<Time> {
  private p: SeriesAttachedParameter<Time> | null = null;
  attached(param: SeriesAttachedParameter<Time>): void { this.p = param; }
  detached(): void { this.p = null; }
  update(): void { this.p?.requestUpdate(); }
  private x(sec: number): number | null {
    if (!this.p || !bars.length) return null;
    const ts = this.p.chart.timeScale();
    const i = bars.findIndex((b) => b.time >= sec);
    const k = i < 0 ? bars.length - 1 : i;
    return ts.logicalToCoordinate((k + (sec - bars[k].time) / 300) as never) as number | null;
  }
  paneViews(): readonly IPrimitivePaneView[] {
    const self = this;
    const renderer: IPrimitivePaneRenderer = {
      draw(target) {
        target.useMediaCoordinateSpace(({ context: ctx }) => {
          const p = self.p;
          if (!p) return;
          const half = Math.max(2, p.chart.timeScale().options().barSpacing / 2);
          const y = (price: number): number | null => p.series.priceToCoordinate(price);
          if (stacksOn.value) {
            const right = p.chart.timeScale().width();
            for (const z of hitList.value) {
              const xa = self.x(Math.floor(z.from / 300_000) * 300); const xb = self.x(Math.floor(z.to / 300_000) * 300 + 3600);
              const ya = y(z.hi + 0.5); const yb = y(z.lo - 0.5);
              if (xa === null || ya === null || yb === null) continue;
              const x1 = Math.min(right, xb ?? right);
              ctx.fillStyle = rgba(COLORS.watch, 0.13);
              ctx.fillRect(xa - half, ya, x1 - xa + half, Math.max(3, yb - ya));
              ctx.strokeStyle = rgba(COLORS.watch, 0.7);
              ctx.strokeRect(Math.round(xa - half) + 0.5, Math.round(ya) + 0.5, Math.round(x1 - xa + half), Math.max(3, Math.round(yb - ya)));
              ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.textAlign = 'left'; ctx.fillStyle = COLORS.watch;
              const back = z.back !== null ? ` · came back ${z.back > 0 ? '+' : ''}${z.back.toFixed(1)}` : '';
              ctx.fillText(`${z.count} stats hit${back}`, xa - half + 4, z.approach > 0 ? yb + 13 : ya - 5);
            }
            const xs = self.x(Math.floor(asOfMs.value / 300_000) * 300);
            if (xs !== null) {
              for (const z of openList.value) {
                const ya = y(z.hi + 0.5); const yb = y(z.lo - 0.5);
                if (ya === null || yb === null) continue;
                ctx.fillStyle = rgba(COLORS.watch, 0.07);
                ctx.fillRect(xs, ya, right - xs, Math.max(3, yb - ya));
                ctx.setLineDash([5, 4]); ctx.strokeStyle = rgba(COLORS.watch, 0.8);
                ctx.strokeRect(Math.round(xs) + 0.5, Math.round(ya) + 0.5, Math.round(right - xs) - 1, Math.max(3, Math.round(yb - ya)));
                ctx.setLineDash([]);
                ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.textAlign = 'right'; ctx.fillStyle = COLORS.watch;
                ctx.fillText(`${z.count} stats stack · ${z.away} pts away`, right - 6, ya - 5);
              }
            }
            ctx.font = '600 12px Inter, system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = COLORS.long;
            for (const l of stats.value) {
              if (l.never || l.hitAt === null) continue;
              const xh = self.x(Math.floor(l.hitAt / 300_000) * 300); const yh = y(l.price);
              if (xh === null || yh === null) continue;
              ctx.fillText('✓', xh, yh + 4);
            }
          }
          for (const t of drawn) {
            const s0 = Math.floor(t.entryMs / 1000 / 300) * 300;
            const s1 = Math.floor(t.exitMs / 1000 / 300) * 300;
            const xa = self.x(s0); const xb = self.x(s1);
            if (xa === null) continue;
            const x0 = xa - half; const x1 = Math.max((xb ?? xa) + half, x0 + 8);
            const ye = y(t.entry); const yt = y(t.entry + TARGET * t.dir); const ys = y(t.entry - STOP * t.dir);
            if (ye === null || yt === null || ys === null) continue;
            const on = selected.value === t;
            ctx.font = '11px Inter, system-ui, sans-serif';
            for (const lv of t.levels) {
              const yy = y(lv.price);
              if (yy === null) continue;
              const a = Math.max(0, x0 - 120);
              ctx.strokeStyle = rgba(COLORS.watch, on ? 0.95 : 0.55);
              ctx.setLineDash([5, 4]);
              ctx.beginPath(); ctx.moveTo(a, Math.round(yy) + 0.5); ctx.lineTo(x1 + 40, Math.round(yy) + 0.5); ctx.stroke();
              ctx.setLineDash([]);
              ctx.fillStyle = rgba(COLORS.watch, on ? 1 : 0.7); ctx.textAlign = 'left';
              ctx.fillText(lv.name, a + 4, yy - 4);
            }
            ctx.fillStyle = rgba(COLORS.long, on ? 0.32 : 0.2);
            ctx.fillRect(x0, Math.min(ye, yt), x1 - x0, Math.abs(yt - ye));
            ctx.fillStyle = rgba(COLORS.short, on ? 0.38 : 0.24);
            ctx.fillRect(x0, Math.min(ye, ys), x1 - x0, Math.abs(ys - ye));
            ctx.strokeStyle = COLORS.fg; ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(x0, ye); ctx.lineTo(x1, ye); ctx.stroke(); ctx.lineWidth = 1;
            ctx.fillStyle = t.dir > 0 ? COLORS.long : COLORS.short;
            ctx.beginPath();
            const ay = t.dir > 0 ? Math.max(ye, ys) + 14 : Math.min(ye, ys) - 14;
            ctx.moveTo(x0, ay);
            ctx.lineTo(x0 - 6, ay + 9 * t.dir); ctx.lineTo(x0 + 6, ay + 9 * t.dir);
            ctx.fill();
            const mark = t.how === 'target' ? '✓' : t.how === 'stop' ? '✕' : '⏱';
            ctx.font = '600 12px Inter, system-ui, sans-serif'; ctx.textAlign = 'left';
            ctx.fillStyle = t.pts > 0 ? COLORS.long : t.pts < 0 ? COLORS.short : COLORS.muted;
            ctx.fillText(`${t.id} ${mark} ${t.pts > 0 ? '+' : ''}${t.pts}`, x0, t.dir > 0 ? Math.min(ye, yt) - 6 : Math.max(ye, yt) + 15);
          }
        });
      },
    };
    return [{ zOrder: () => 'normal', renderer: () => renderer }];
  }
}
const primitive = new TradesPrimitive();

function setupChart(): void {
  if (!chartEl.value) return;
  const fm = createChartTimeFormatters('America/New_York');
  chart = createChart(chartEl.value, {
    autoSize: true,
    layout: { background: { color: '#0c0f15' }, textColor: COLORS.muted, attributionLogo: false },
    grid: { vertLines: { color: '#151a24' }, horzLines: { color: '#151a24' } },
    rightPriceScale: { borderColor: '#232a37' },
    timeScale: { borderColor: '#232a37', timeVisible: true, secondsVisible: false, rightOffset: 6, tickMarkFormatter: fm.tickMarkFormatter },
    localization: { locale: 'en-US', timeFormatter: fm.timeFormatter },
    crosshair: { mode: 0 },
  });
  series = chart.addSeries(CandlestickSeries, {
    upColor: '#cfd5de', downColor: '#4a5263', borderVisible: false, wickUpColor: COLORS.muted, wickDownColor: COLORS.muted,
    priceLineVisible: false, lastValueVisible: false,
  });
  series.attachPrimitive(primitive);
  chart.subscribeCrosshairMove((param) => {
    const b = param.seriesData.get(series as ISeriesApi<'Candlestick'>) as { open: number; high: number; low: number; close: number } | undefined;
    asOf.value = param.time ? Number(param.time) * 1000 : null;
    primitive.update();
    legend.value = b && param.time
      ? `${clock(Number(param.time) * 1000)}  O ${b.open}  H ${b.high}  L ${b.low}  C ${b.close}`
      : '5-min candles · New York time';
  });
}

let dayRequest = 0;
async function showDay(d: string): Promise<void> {
  selected.value = null;
  drawn = [];
  stats.value = [];
  candleData.value = [];
  if (!d || !series || !chart) { series?.setData([]); return; }
  const req = ++dayRequest;
  const market = markets.value.find((m) => m.symbol === symbol.value);
  const { startMs, endMs } = cmeDayBounds(d);
  try {
    const candles = await fetchCandles(symbol.value, 'M5', { startMs, endMs, exchange: market?.exchange ?? null, limit: 400 });
    if (req !== dayRequest) return;
    bars = candles.map((c) => ({ time: c.time }));
    candleData.value = candles.map((c) => ({ time: c.time, high: c.high, low: c.low, close: c.close }));
    asOf.value = null;
    try {
      const plan = await fetchGamePlan(symbol.value, { day: d, exchange: market?.exchange ?? null });
      if (req !== dayRequest) return;
      stats.value = plan.levels.map((l) => ({ label: l.label, price: l.price, odds: l.odds, hitAt: l.hitAt, frm: l.frm, until: l.until, never: l.never }));
    } catch {
      stats.value = [];
    }
    series.setData(candles.map((c) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close })));
    drawn = dayTrades.value;
    const first = drawn[0]; const last = drawn[drawn.length - 1];
    if (first && last) {
      const i0 = bars.findIndex((b) => b.time >= first.entryMs / 1000 - 3 * 3600);
      const i1 = bars.findIndex((b) => b.time >= last.exitMs / 1000 + 3600);
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, i0), to: (i1 < 0 ? bars.length : i1) + 4 });
    }
    primitive.update();
  } catch (e) {
    status.value = `Couldn't load candles for ${d}. ${(e as Error).message}`;
    failed.value = true;
  }
}

function focusTrade(t: SetupTrade): void {
  selected.value = t;
  const i = bars.findIndex((b) => b.time >= t.entryMs / 1000);
  chart?.timeScale().setVisibleLogicalRange({ from: Math.max(0, i - 40), to: Math.min(bars.length + 5, i + 40) });
  primitive.update();
}

async function load(): Promise<void> {
  const market = markets.value.find((m) => m.symbol === symbol.value);
  const now = Date.now();
  const startMs = period.value === 'ytd' ? Date.UTC(2026, 0, 1) : now - Number(period.value) * 86_400_000;
  status.value = `Running the setups on ${symbol.value} 1-minute data…`;
  failed.value = false;
  try {
    const res = await requestIndicator(SETUPS_INDICATOR_ID, {
      symbol: symbol.value, timeframe: 'M1', exchange: market?.exchange ?? null, startMs, endMs: now,
    });
    trades.value = tradesFrom(res.data.indicator_data);
    status.value = trades.value.length ? '' : `No setups fired on ${symbol.value} in this period, or there's no 1-minute data for it yet.`;
    day.value = days.value[days.value.length - 1] ?? '';
    await showDay(day.value);
  } catch (e) {
    trades.value = [];
    status.value = `Couldn't run the setups: ${(e as Error).message}. Check that the app's services are running.`;
    failed.value = true;
  }
}

watch(day, (d) => { void showDay(d); });
watch([stacksOn, minCount, width, stats], () => primitive.update());
watch(shown, () => { void showDay(day.value); });

onMounted(async () => {
  setupChart();
  if (!marketsStore.all.length) await marketsStore.fetch();
  if (!markets.value.some((m) => m.symbol === symbol.value)) symbol.value = markets.value.find((m) => m.symbol === 'ES')?.symbol ?? markets.value[0]?.symbol ?? 'ES';
  await load();
});
onBeforeUnmount(() => { chart?.remove(); chart = null; });
</script>

<style scoped>
.setups-page {
  --bg: #0c0f15; --panel: #131822; --line: #232a37; --fg: #e8ebf0; --muted: #8b93a1;
  --long: #2fbf8f; --short: #e0566c; --watch: #e3ad42; --accent: #6f9bff;
  height: 100%; overflow-y: auto; box-sizing: border-box; padding: 16px 20px 32px; background: var(--bg); color: var(--fg);
  display: flex; flex-direction: column; gap: 12px; font-size: 14px;
}
.setups-page > * { flex-shrink: 0; }
.spacer { flex: 1; }
.inline { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 13px; }
.inline select { padding: 4px 8px; }
.stacks { display: flex; flex-direction: column; gap: 8px; }
.stacks h2 { margin: 4px 0 0; font-size: 15px; font-weight: 600; }
.stack { background: var(--panel); border: 1px solid rgba(227, 173, 66, 0.45); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; }
.stack.ahead { border-style: dashed; }
.stack b { font-size: 13px; color: var(--watch); }
.stack p { margin: 0; color: var(--muted); font-size: 13px; }
.stack .win { color: var(--long); font-weight: 600; } .stack .loss { color: var(--short); font-weight: 600; }
.head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: flex-end; }
h1 { margin: 0; font-size: 22px; font-weight: 600; }
.sub { margin: 2px 0 0; color: var(--muted); max-width: 80ch; }
.controls { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
.ctl { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
select, .btn { font: 500 13px inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 7px 12px; cursor: pointer; text-transform: none; letter-spacing: 0; }
.btn:disabled { opacity: 0.4; cursor: default; }
.status { margin: 0; color: var(--muted); }
.status.err { color: var(--short); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: flex; flex-direction: column; gap: 2px; text-align: left; font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; cursor: pointer; flex: 1 1 150px; min-width: 150px; }
.chip[aria-pressed='false'] { opacity: 0.45; }
.chip b { font-size: 13px; font-weight: 600; }
.chip .meta { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.tag { display: inline-block; font-size: 11px; font-weight: 600; border-radius: 4px; padding: 0 5px; margin-right: 6px; }
.tag.long { background: rgba(47, 191, 143, 0.18); color: var(--long); }
.tag.short { background: rgba(224, 86, 108, 0.18); color: var(--short); }
.bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.dayname { font-size: 15px; font-weight: 600; }
.daysum { color: var(--muted); font-variant-numeric: tabular-nums; }
.stage { position: relative; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.chart { height: min(60vh, 620px); min-height: 360px; }
.legend { position: absolute; left: 10px; top: 8px; z-index: 3; font-size: 12px; color: var(--muted); pointer-events: none; font-variant-numeric: tabular-nums; }
.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
.trade { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; cursor: pointer; min-width: 0; }
.trade.on, .trade:focus-visible { border-color: var(--accent); outline: none; }
.trade .top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.trade .name { font-size: 13px; font-weight: 600; }
.res { font-weight: 600; font-variant-numeric: tabular-nums; color: var(--muted); }
.res.win { color: var(--long); } .res.loss { color: var(--short); }
.trade p { margin: 0; color: var(--muted); font-size: 13px; }
.lv { font-size: 12px; color: var(--watch); }
.how { color: var(--muted); font-size: 13px; max-width: 90ch; margin: 0; }
</style>
