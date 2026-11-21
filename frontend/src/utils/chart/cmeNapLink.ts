import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';
import { watch, type WatchStopHandle } from 'vue';

import { fetchCandles } from '@/api/candleClient';
import { useCmeNapStore } from '@/stores/cmeNapStore';
import type { ChartCandle } from '@/types/contracts';
import { apiSizes, CATCH_UP_HOLD_MIN, CATCH_UP_MIN, catchUp, fetchHyperliquidBars, findNaps, lineUp, NAP_TWIN, type Bar, type CatchUp, type Nap, type NapResult } from '@/utils/cmeNap';

import type { ChartManager, ChartDataPoint, ManagedSeriesApi } from './ChartManager';

const SERIES_KEY = 'cme-nap-hyperliquid';
const PURPLE = '#b07cff';

/** Gray "CME closed" zones, the reopen dots and a one-line score, drawn on the purple line's series. */
class NapPrimitive implements ISeriesPrimitive<Time> {
  private param: SeriesAttachedParameter<Time> | null = null;
  naps: NapResult[] = [];
  trades = new Map<number, CatchUp | 'none'>(); // by the nap's openT; 'none' = gap under the minimum
  barMinutes = 1;
  cursor = Number.POSITIVE_INFINITY;
  symbol = '';
  twin = '';

  attached(p: SeriesAttachedParameter<Time>): void { this.param = p; }
  detached(): void { this.param = null; }
  update(): void { this.param?.requestUpdate(); }

  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = { draw: (t) => this.draw(t) };
    return [{ zOrder: () => 'bottom', renderer: () => renderer }];
  }

  private draw(target: CanvasRenderingTarget2D): void {
    const p = this.param;
    if (!p) return;
    const ts = p.chart.timeScale();
    const x = (ms: number) => ts.timeToCoordinate(Math.floor(ms / 1000) as Time);
    const y = (px: number) => p.series.priceToCoordinate(px);
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const half = Math.max(1, ts.options().barSpacing / 2);
      for (const n of this.naps) {
        if (n.closeT > this.cursor) continue;
        const x0 = x(n.closeT);
        const shownPts = n.line.filter(([t]) => t <= this.cursor);
        const lastT = shownPts.length ? shownPts[shownPts.length - 1][0] : n.closeT;
        // still asleep at the cursor: the zone runs to the last purple point shown
        const xr = n.openT <= this.cursor ? x(n.openT) : x(lastT);
        if (x0 === null || xr === null) continue;
        const x1 = xr;
        const left = x0 + half;
        const right = Math.min(n.openT <= this.cursor ? x1 - half : x1 + half, mediaSize.width);
        if (right <= left) continue;
        ctx.fillStyle = 'rgba(139, 147, 163, 0.12)';
        ctx.fillRect(left, 0, right - left, mediaSize.height);
        const sharp = n.barMinutes === 1 ? '1-min' : n.barMinutes < 60 ? `${n.barMinutes}-min, blurrier` : `${n.barMinutes / 60}-hour, rough`;
        const lines = [`CME closed · Hyperliquid ${this.twin} still trading (${sharp})`];
        const shown = n.line.filter(([t]) => t <= this.cursor);
        const lastPx = shown.length ? shown[shown.length - 1][1] : null;
        if (lastPx !== null && shown.length > 1) {
          const moved = (n.openT <= this.cursor && n.hlAtOpen !== null ? n.hlAtOpen : lastPx) - n.closePx;
          lines.push(`Hyperliquid moved ${moved >= 0 ? '+' : '−'}${Math.abs(moved).toFixed(2)} pts while CME slept`);
        }
        if (n.openT <= this.cursor && n.hlAtOpen !== null) {
          const opened = n.openPx - n.closePx;
          lines.push(`${this.symbol} opened ${opened >= 0 ? '+' : '−'}${Math.abs(opened).toFixed(2)} · ${Math.abs(n.openPx - n.hlAtOpen).toFixed(2)} pts from the purple dot`);
        }
        ctx.font = '600 11.5px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        const w = Math.max(...lines.map((s) => ctx.measureText(s).width)) + 12;
        const bx = Math.max(4, Math.min(left + 6, mediaSize.width - w - 70));
        ctx.fillStyle = 'rgba(19, 23, 34, 0.88)';
        ctx.fillRect(bx, 40, w, lines.length * 16 + 8);
        lines.forEach((s, i) => { ctx.fillStyle = i === 0 ? '#c9ced6' : i === 1 ? PURPLE : '#ffffff'; ctx.fillText(s, bx + 6, 44 + i * 16); });
        // dashed "fell asleep" line
        const yc = y(n.closePx);
        if (yc !== null) {
          ctx.setLineDash([5, 4]); ctx.strokeStyle = 'rgba(200, 206, 214, 0.5)'; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(x0, Math.round(yc) + 0.5); ctx.lineTo(right, Math.round(yc) + 0.5); ctx.stroke(); ctx.setLineDash([]);
        }
        // catch-up trade
        const tr = this.trades.get(n.openT);
        if (n.openT <= this.cursor && tr === 'none' && n.hlAtOpen !== null) {
          const yo = y(n.openPx);
          if (yo !== null) {
            const t = `No trade · ${Math.abs(n.openPx - n.hlAtOpen).toFixed(2)} pts from the dot`;
            ctx.font = '11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
            const w = ctx.measureText(t).width; ctx.fillStyle = 'rgba(19, 23, 34, 0.85)'; ctx.fillRect(x1 + 10, yo + 10, w + 8, 16);
            ctx.fillStyle = '#9aa3b2'; ctx.fillText(t, x1 + 14, yo + 18);
          }
        }
        if (n.openT <= this.cursor && tr && tr !== 'none') {
          const spacing = ts.options().barSpacing;
          const bx0 = x1 - half;
          const bx1 = Math.min(mediaSize.width, x1 + (CATCH_UP_HOLD_MIN / this.barMinutes) * spacing - half);
          const ye = y(tr.entry); const yt = y(tr.target); const ys = y(tr.stop);
          if (ye !== null && yt !== null && ys !== null && bx1 > bx0) {
            ctx.fillStyle = 'rgba(47, 191, 143, 0.20)'; ctx.fillRect(bx0, Math.min(ye, yt), bx1 - bx0, Math.abs(yt - ye));
            ctx.fillStyle = 'rgba(224, 86, 108, 0.24)'; ctx.fillRect(bx0, Math.min(ye, ys), bx1 - bx0, Math.abs(ys - ye));
            const title = `Catch-up ${tr.dir > 0 ? '▲' : '▼'} to the purple dot · ${tr.dist.toFixed(2)} pts`;
            ctx.font = '600 12px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
            const ty = Math.max(16, Math.min(yt, ys) - 4); const tw = ctx.measureText(title).width;
            ctx.fillStyle = 'rgba(19, 23, 34, 0.88)'; ctx.fillRect(bx0, ty - 16, tw + 10, 18);
            ctx.fillStyle = '#ffffff'; ctx.fillText(title, bx0 + 5, ty - 1);
            // result only once the trade is over
            if (tr.exitT <= this.cursor) {
              const xe = x(tr.exitT);
              const yr = y(tr.how === 'target' ? tr.target : tr.how === 'stop' ? tr.stop : tr.entry + tr.pts * tr.dir);
              if (xe !== null && yr !== null) {
                const tag = `${tr.how === 'target' ? '✓' : tr.how === 'stop' ? '✗' : '⏱'} ${tr.pts >= 0 ? '+' : '−'}${Math.abs(tr.pts).toFixed(2)} pts${tr.how === 'time' ? ' at 60 min' : ''}`;
                ctx.font = '700 12.5px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'; ctx.textBaseline = 'middle';
                const w = ctx.measureText(tag).width;
                ctx.fillStyle = tr.pts >= 0 ? 'rgba(47, 182, 124, 0.95)' : 'rgba(224, 87, 74, 0.95)';
                ctx.fillRect(xe + 8, yr - 11, w + 12, 22);
                ctx.fillStyle = '#0f121a'; ctx.fillText(tag, xe + 14, yr + 0.5);
              }
            }
          }
        }
        // wake-up dots
        if (n.openT <= this.cursor && n.hlAtOpen !== null) {
          const yh = y(n.hlAtOpen); const yo = y(n.openPx);
          if (yh !== null && yo !== null) {
            ctx.strokeStyle = 'rgba(227, 173, 66, 0.9)'; ctx.setLineDash([3, 3]);
            ctx.beginPath(); ctx.moveTo(x1, yh); ctx.lineTo(x1, yo); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = PURPLE; ctx.beginPath(); ctx.arc(x1, yh, 5, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.arc(x1, yo, 5, 0, Math.PI * 2); ctx.fill();
          }
        }
      }
    });
  }
}

/**
 * Keeps the "CME closed" overlay on one chart: finds the closures in the loaded candles, loads
 * Hyperliquid's price for each (sharpest source first) and draws it as a purple line. The line's
 * points inside each closure give that stretch room on the time axis, so the candles stay as they are.
 */
export class CmeNapLink {
  private readonly prim = new NapPrimitive();
  private series: ManagedSeriesApi | null = null;
  private readonly cache = new Map<string, NapResult | 'loading' | 'none'>();
  private stop: WatchStopHandle | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastKey = '';

  constructor(
    private readonly host: {
      manager(): Pick<ChartManager, 'addSeries' | 'setSeriesData' | 'removeSeries' | 'series'> | null;
      candles(): readonly ChartCandle[];
      symbol(): string | null;
      barMinutes(): number;
      cursorMs(): number; // Replay cursor, or +Infinity live
      onChange(): void; // the line changed (Replay redraws its curtain and steps)
    },
  ) {
    const store = useCmeNapStore();
    this.stop = watch(() => store.visible, () => this.refresh(true));
    this.timer = setInterval(() => this.refresh(false), 5000);
  }

  private twin(): string | null {
    const s = (this.host.symbol() ?? '').toUpperCase();
    return NAP_TWIN[s] ?? null;
  }

  /** Times of the purple line's points (Replay steps through them too). */
  times(): number[] {
    return this.prim.naps.flatMap((n) => n.line.map(([t]) => t));
  }

  refresh(force: boolean): void {
    const store = useCmeNapStore();
    const twin = this.twin();
    const minutes = this.host.barMinutes();
    if (!store.visible || !twin || minutes > 60) { this.clear(); return; }
    const candles = this.host.candles();
    const key = `${twin}|${minutes}|${candles.length}|${candles[0]?.timestamp_ms}|${candles[candles.length - 1]?.timestamp_ms}|${this.host.cursorMs()}`;
    if (!force && key === this.lastKey) return;
    this.lastKey = key;
    const naps = findNaps(candles, minutes * 60_000);
    this.prim.symbol = (this.host.symbol() ?? '').toUpperCase();
    this.prim.twin = twin;
    for (const n of naps) void this.load(twin, n, minutes);
    this.draw(naps, twin, minutes);
  }

  private napKey(twin: string, n: Nap, minutes: number): string { return `${twin}|${minutes}|${n.closeT}|${n.openT}`; }

  private async load(twin: string, n: Nap, minutes: number): Promise<void> {
    const k = this.napKey(twin, n, minutes);
    if (this.cache.has(k)) return;
    this.cache.set(k, 'loading');
    const chartBar = minutes * 60_000;
    let result: NapResult | null = null;
    try {
      // 1. the app's own 1-minute recording of Hyperliquid
      const rows = await fetchCandles(twin, 'M1', { startMs: n.closeT - 30 * 60_000, endMs: n.openT + chartBar, limit: 5000, exchange: 'HYPERLIQUID' });
      const bars: Bar[] = rows.map((r) => ({ t: r.timestamp_ms, c: Number(r.close) }));
      if (bars.length && bars[0].t <= n.closeT && bars[bars.length - 1].t >= n.openT - chartBar) {
        result = lineUp(n, bars, 1, chartBar);
      }
    } catch { /* fall through to Hyperliquid's API */ }
    if (!result || !result.line.length) {
      for (const size of apiSizes(Date.now() - n.openT)) {
        if (size.minutes > Math.max(60, minutes) && !n.weekend) break; // an hour-long break needs finer bars than an hour
        try {
          const bars = await fetchHyperliquidBars(twin, size.interval, n.closeT - 4 * size.minutes * 60_000, n.openT + size.minutes * 60_000);
          if (bars.length && bars[0].t <= n.closeT) { result = lineUp(n, bars, size.minutes, chartBar); if (result.line.length) break; }
        } catch { /* try the next size */ }
      }
    }
    this.cache.set(k, result && result.line.length ? result : 'none');
    this.refresh(true);
  }

  private draw(naps: Nap[], twin: string, minutes: number): void {
    const manager = this.host.manager();
    if (!manager) return;
    const cursor = this.host.cursorMs();
    const ready = naps.map((n) => this.cache.get(this.napKey(twin, n, minutes))).filter((r): r is NapResult => typeof r === 'object');
    this.prim.naps = ready;
    this.prim.barMinutes = minutes;
    // catch-up trades (NQ / MNQ): worked out on all loaded candles, shown up to the cursor
    const minGap = CATCH_UP_MIN[(this.host.symbol() ?? '').toUpperCase()];
    const candles = this.host.candles();
    this.prim.trades.clear();
    let done = 0; let won = 0; let total = 0;
    for (const n of ready) {
      if (minGap === undefined) continue;
      const tr = catchUp(n, candles, minGap);
      this.prim.trades.set(n.openT, tr ?? 'none');
      if (tr && tr.exitT <= cursor) { done += 1; total += tr.pts; if (tr.pts > 0) won += 1; }
    }
    useCmeNapStore().tradeScore = minGap === undefined || !done ? '' : `Catch-up trades: ${won} of ${done} won · ${total >= 0 ? '+' : '−'}${Math.abs(total).toFixed(2)} pts`;
    this.prim.cursor = cursor;
    const pts: ChartDataPoint[] = [];
    for (const n of ready) {
      const shown = n.line.filter(([t]) => t <= cursor);
      if (shown.length < 2) continue;
      // break the line between closures on the CME bar before each one (a time the chart already has)
      if (pts.length) pts.push({ time: Math.floor((n.closeT - minutes * 60_000) / 1000) } as unknown as ChartDataPoint);
      for (const [t, v] of shown) pts.push({ time: Math.floor(t / 1000), value: v });
    }
    const dedup = pts.filter((q, i) => i === 0 || q.time > pts[i - 1].time);
    if (this.series && !manager.series.has(SERIES_KEY)) this.series = null; // the chart was rebuilt
    if (!this.series) {
      this.series = manager.addSeries(SERIES_KEY, 'line', dedup, {
        color: PURPLE, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      } as never);
      this.series?.attachPrimitive(this.prim);
    } else {
      manager.setSeriesData(SERIES_KEY, dedup);
    }
    const store = useCmeNapStore();
    store.status = ready.length ? `${ready.length} CME closures shown with Hyperliquid ${twin}` : naps.length ? 'Loading Hyperliquid…' : 'No CME closure in view';
    this.prim.update();
    this.host.onChange();
  }

  private clear(): void {
    this.lastKey = '';
    if (!this.series) return;
    const manager = this.host.manager();
    try { this.series.detachPrimitive(this.prim); } catch { /* already gone */ }
    manager?.removeSeries(SERIES_KEY);
    this.series = null;
    this.prim.naps = [];
    this.host.onChange();
  }

  destroy(): void {
    this.stop?.();
    if (this.timer) clearInterval(this.timer);
    this.clear();
  }
}
