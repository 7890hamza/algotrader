import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, Logical, SeriesAttachedParameter, Time } from 'lightweight-charts';
import { watch, type WatchStopHandle } from 'vue';

import { useDailyCandleStore, type DcWho } from '@/stores/dailyCandleStore';
import { ptClock, readDays, scoreDays, STAT_WINDOWS, type DayRead, type DcBar, type Verdict } from '@/utils/dailyCandle';

import type { ManagedSeriesApi } from './ChartManager';

const AUS = '#e3a33d';
const RIL = '#2bb5b0';
const Q1 = '#8f7cf0';
const GREY = '#9aa3b2';
const UP = '#2fb67c';
const DN = '#e0574a';
const FONT = (w: number, px: number) => `${w} ${px}px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`;
const f2 = (v: number) => v.toFixed(2);
const mark = (v: Verdict) => (v === 'right' ? '✓' : v === 'wrong' ? '✗' : '');

/** Draws Austin's levels and Riley's boxes for each loaded day, plus a plain-English card for the latest day. */
class DailyCandlePrimitive implements ISeriesPrimitive<Time> {
  private param: SeriesAttachedParameter<Time> | null = null;
  days: DayRead[] = [];
  times: number[] = []; // loaded bar times (ms), to place any moment on the time axis
  barMs = 60_000;
  who: DcWho = 'both';
  score = '';
  note = '';

  attached(p: SeriesAttachedParameter<Time>): void { this.param = p; }
  detached(): void { this.param = null; }
  update(): void { this.param?.requestUpdate(); }
  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = { draw: (t) => this.draw(t) };
    return [{ zOrder: () => 'top', renderer: () => renderer }];
  }

  /** x for any time: between loaded bars by position, past the last bar by bar width. */
  private x(ms: number): number | null {
    const p = this.param; const n = this.times.length;
    if (!p || !n) return null;
    let lo = 0; let hi = n - 1;
    if (ms >= this.times[hi]) return p.chart.timeScale().logicalToCoordinate((hi + (ms - this.times[hi]) / this.barMs) as Logical);
    if (ms <= this.times[0]) return p.chart.timeScale().logicalToCoordinate(((ms - this.times[0]) / this.barMs) as Logical);
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (this.times[m] <= ms) lo = m; else hi = m; }
    const frac = Math.min(1, (ms - this.times[lo]) / this.barMs);
    return p.chart.timeScale().logicalToCoordinate((lo + frac) as Logical);
  }

  private draw(target: CanvasRenderingTarget2D): void {
    const p = this.param;
    if (!p) return;
    const y = (v: number) => p.series.priceToCoordinate(v);
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width; const H = mediaSize.height;
      const at = (d: DayRead, dm: number) => this.x(d.start + dm * 60_000);
      const showA = this.who !== 'riley'; const showR = this.who !== 'austin';

      const hline = (d: DayRead, price: number, dm0: number, color: string, label: string, dash: number[] = []) => {
        const x0 = at(d, dm0); const x1 = at(d, 1320); const yy = y(price);
        if (x0 === null || x1 === null || yy === null || x1 < 0 || x0 > W) return;
        ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash(dash);
        ctx.beginPath(); ctx.moveTo(x0, Math.round(yy) + 0.5); ctx.lineTo(x1, Math.round(yy) + 0.5); ctx.stroke(); ctx.setLineDash([]);
        ctx.font = FONT(600, 11); ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillStyle = color;
        ctx.fillText(`${label} ${f2(price)}`, Math.min(x1, W - 4) - 2, yy - 2);
      };
      const box = (d: DayRead, dm0: number, dm1: number, hi: number, lo: number, color: string, label: string) => {
        const x0 = at(d, dm0); const x1 = at(d, dm1); const y0 = y(hi); const y1 = y(lo);
        if (x0 === null || x1 === null || y0 === null || y1 === null || x1 < 0 || x0 > W) return;
        ctx.fillStyle = `${color}26`; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
        ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
        ctx.font = FONT(700, 11); ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.fillStyle = color;
        ctx.fillText(label, x0 + 2, y0 - 3);
      };
      const tag = (x: number, yy: number, text: string, color: string, below = false) => {
        ctx.font = FONT(700, 12); const w = ctx.measureText(text).width + 12;
        const bx = Math.max(2, Math.min(x - w / 2, W - w - 2)); const by = below ? yy + 8 : yy - 30;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.9)'; ctx.fillRect(bx, by, w, 22);
        ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.strokeRect(bx + 0.5, by + 0.5, w - 1, 21);
        ctx.fillStyle = color; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(text, bx + 6, by + 11.5);
      };

      for (const d of this.days) {
        const xs = at(d, 0); const xe = at(d, 1320);
        if (xs === null || xe === null || xe < 0 || xs > W) continue;
        const A = d.austin; const R = d.riley;
        if (showA) {
          for (const [a, b] of STAT_WINDOWS) {
            const x0 = at(d, a); const x1 = at(d, b);
            if (x0 === null || x1 === null) continue;
            ctx.fillStyle = 'rgba(227, 163, 61, 0.08)'; ctx.fillRect(x0, 0, x1 - x0, H);
            ctx.font = FONT(600, 10.5); ctx.fillStyle = 'rgba(227, 163, 61, 0.8)'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
            ctx.fillText(`stat ${ptClock(a)}`, x0 + 3, H - 4);
          }
          if (A.p12) {
            hline(d, A.p12.hi, 720, AUS, 'P12 high'); hline(d, A.p12.lo, 720, AUS, 'P12 low');
            hline(d, (A.p12.hi + A.p12.lo) / 2, 720, AUS, 'P12 mid', [5, 4]);
          }
          if (A.midnightOpen !== null) hline(d, A.midnightOpen, 360, GREY, 'midnight open', [2, 3]);
          if (A.q1) box(d, 720, 870, A.q1.hi, A.q1.lo, Q1, 'Q1');
          for (const [e, isHigh] of [[A.high, true], [A.low, false]] as const) {
            if (!e) continue;
            const ex = this.x(e.t + this.barMs / 2); const ey = y(e.price);
            if (ex === null || ey === null) continue;
            const c = e.inStat ? UP : GREY;
            ctx.strokeStyle = c; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(ex, ey, 7, 0, Math.PI * 2); ctx.stroke();
            ctx.font = FONT(700, 11.5); ctx.fillStyle = c; ctx.textAlign = 'center'; ctx.textBaseline = isHigh ? 'bottom' : 'top';
            ctx.fillText(`${isHigh ? 'high' : 'low'}: ${e.inStat ? 'in stat ✓' : 'not in stat'}`, ex, isHigh ? ey - 10 : ey + 10);
          }
          const xo = at(d, 930); const yo = A.priceAtOpen !== null ? y(A.priceAtOpen) : null;
          if (A.lean !== null && xo !== null && yo !== null) {
            const call = A.lean > 0 ? 'Austin: looks UP ▲' : A.lean < 0 ? 'Austin: looks DOWN ▼' : 'Austin: no lean';
            tag(xo, A.lean < 0 ? yo + 40 : yo - 20, `${call} ${mark(A.verdict)}`, A.verdict === 'wrong' ? DN : A.verdict === 'right' ? UP : AUS, A.lean < 0);
          }
        }
        if (showR) {
          for (const [a, b, dir, name] of [[120, 360, R.asia, 'Asia'], [480, 660, R.london, 'London']] as const) {
            const x0 = at(d, a); const x1 = at(d, b);
            if (x0 === null || x1 === null || dir === null) continue;
            ctx.fillStyle = 'rgba(43, 181, 176, 0.06)'; ctx.fillRect(x0, 0, x1 - x0, H);
            ctx.font = FONT(700, 13); ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = dir > 0 ? UP : dir < 0 ? DN : GREY;
            ctx.fillText(`${dir > 0 ? '▲' : dir < 0 ? '▼' : '•'} ${name}`, (x0 + x1) / 2, 30);
          }
          if (R.night) {
            const xl = at(d, 660);
            if (xl !== null) { ctx.font = FONT(700, 12); ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.fillStyle = RIL; ctx.fillText(`${R.night} night`, xl + 4, 30); }
          }
          if (R.sixBox) {
            box(d, 720, 780, R.sixBox.hi, R.sixBox.lo, RIL, '6 AM hr');
            hline(d, (R.sixBox.hi + R.sixBox.lo) / 2, 780, RIL, '6AM mid', [5, 4]);
          }
          if (R.openBox) box(d, 930, 960, R.openBox.hi, R.openBox.lo, RIL, 'open box');
          if (R.brk) {
            for (const pl of R.pLines) hline(d, pl.price, R.brk.dm, RIL, `${pl.name}${pl.hit ? ' ✓' : ''}`, [6, 4]);
            const bx = this.x(R.brk.t - this.barMs / 2); const by = y(R.brk.edge);
            if (bx !== null && by !== null) {
              ctx.strokeStyle = RIL; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(bx, by, 7, 0, Math.PI * 2); ctx.stroke();
              const call = R.call === 'with' ? `Riley: go with the break ${R.brk.dir > 0 ? '▲' : '▼'}` : R.call === 'fade' ? `Riley: fade the break ${R.brk.dir > 0 ? '▼' : '▲'}` : 'Riley: break';
              tag(bx + 70, by, `${call} ${mark(R.verdict)}`, R.verdict === 'wrong' ? DN : R.verdict === 'right' ? UP : RIL, R.brk.dir < 0);
            }
          }
        }
      }

      // the card: latest day, in plain words
      const d = this.days[this.days.length - 1];
      const lines: [string, string][] = [];
      if (this.note) lines.push([this.note, GREY]);
      else if (d) {
        lines.push([`Daily candle · ${new Date(`${d.day}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })}`, '#ffffff']);
        if (showA) lines.push([`Austin: ${d.austin.why} ${mark(d.austin.verdict)}`, AUS]);
        if (showR) lines.push([`Riley: ${d.riley.night ? `${d.riley.night} night. ` : ''}${d.riley.why} ${mark(d.riley.verdict)}`, RIL]);
        if (this.score) lines.push([this.score, '#c9ced6']);
      }
      if (!lines.length) return;
      ctx.font = FONT(600, 12);
      const w = Math.max(...lines.map(([s]) => ctx.measureText(s).width)) + 16;
      const bx = Math.max(8, (W - w) / 2);
      ctx.fillStyle = 'rgba(19, 23, 34, 0.92)'; ctx.fillRect(bx, 52, w, lines.length * 18 + 10);
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      lines.forEach(([s, c], i) => { ctx.fillStyle = c; ctx.font = FONT(i === 0 ? 700 : 600, 12); ctx.fillText(s, bx + 8, 58 + i * 18); });
    });
  }
}

/**
 * "Daily candle" overlay: how Austin (levels + stat windows) and Riley (timed boxes + measured runs)
 * read each day on the chart. No trades. In Replay it only uses candles up to the cursor.
 */
export class DailyCandleLink {
  private readonly prim = new DailyCandlePrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private stop: WatchStopHandle | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private lastKey = '';

  constructor(
    private readonly host: {
      getSeries(): ManagedSeriesApi | null;
      candles(): readonly { timestamp_ms: number; open: number | string; high: number | string; low: number | string; close: number | string }[];
      barMinutes(): number;
      cursorMs(): number;
    },
  ) {
    const store = useDailyCandleStore();
    this.stop = watch(() => [store.visible, store.who] as const, () => { this.syncSeries(); this.render(true); });
    this.timer = setInterval(() => this.render(false), 2000);
  }

  syncSeries(): void {
    const store = useDailyCandleStore();
    const series = store.visible ? this.host.getSeries() : null;
    if (series === this.attachedTo) return;
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* already gone */ }
    this.attachedTo = series;
    series?.attachPrimitive?.(this.prim);
    this.render(true);
  }

  /** Attach again so it draws above Replay's curtain. */
  reattach(): void {
    const series = this.attachedTo;
    if (!series) return;
    try { series.detachPrimitive(this.prim); } catch { /* not attached */ }
    series.attachPrimitive?.(this.prim);
    this.render(true);
  }

  private render(force: boolean): void {
    const store = useDailyCandleStore();
    if (!store.visible) { store.score = ''; return; }
    if (this.attachedTo !== this.host.getSeries()) { this.syncSeries(); return; }
    const candles = this.host.candles(); const minutes = this.host.barMinutes(); const cursor = this.host.cursorMs();
    const key = `${candles.length}|${candles[candles.length - 1]?.timestamp_ms}|${candles[candles.length - 1]?.close}|${minutes}|${cursor}|${store.who}`;
    if (!force && key === this.lastKey) return;
    this.lastKey = key;
    this.prim.who = store.who;
    this.prim.barMs = minutes * 60_000;
    this.prim.times = candles.map((c) => c.timestamp_ms);
    if (minutes > 5) {
      this.prim.days = []; this.prim.note = 'Daily candle: switch to a 1- or 5-minute chart'; store.score = '';
    } else {
      const bars: DcBar[] = candles.map((c) => ({ t: c.timestamp_ms, o: Number(c.open), h: Number(c.high), l: Number(c.low), c: Number(c.close) }));
      this.prim.days = readDays(bars, minutes, cursor);
      this.prim.note = this.prim.days.length ? '' : 'Daily candle: no full day loaded yet';
      const s = scoreDays(this.prim.days.filter((d) => d.done));
      const part = (n: string, x: { right: number; calls: number }) => `${n} ${x.right} of ${x.calls}`;
      store.score = s.austin.calls || s.riley.calls ? `Went their way: ${part('Austin', s.austin)} · ${part('Riley', s.riley)}` : '';
      this.prim.score = store.score ? `${store.score} (finished days on the chart)` : '';
    }
    this.prim.update();
  }

  destroy(): void {
    this.stop?.();
    if (this.timer) clearInterval(this.timer);
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* already detached */ }
    this.attachedTo = null;
  }
}
