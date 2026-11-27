import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, Logical, SeriesAttachedParameter, Time } from 'lightweight-charts';
import { watch, type WatchStopHandle } from 'vue';

import { useGexStore } from '@/stores/gexStore';

import type { ManagedSeriesApi } from './ChartManager';
import { timeToLogical } from './drawings';
import { cmeClock } from '@/utils/dailyCandle';

/** One refresh of the option walls (scripts/oi_walls.py), already in futures prices. */
export interface WallSnap { t: number; outerCall: number | null; call: number | null; flip: number | null; put: number | null; outerPut: number | null; pin?: number | null; regime?: string | null; etf: string; ratio: number; expirations: string[]; zone?: number }
export interface VwapBar { t: number; o: number; h: number; l: number; c: number; v: number }
export interface WallsFile { market: string; days: Record<string, WallSnap[]>; latest: WallSnap }

/** Stepped segments for one level: [start ms, end ms, price], one per stretch the level stayed put. */
/**
 * VWAP from the 9:30 New York open to 4 PM, each day, with the formula of the ama Current Day
 * VWAP in NinjaTrader: each bar's price = average of (high + low) / 2 and (open + close) / 2,
 * weighted by volume. Bars outside 9:30-4 PM get null.
 */
export function rthVwap(bars: readonly VwapBar[]): (number | null)[] {
  const out: (number | null)[] = [];
  let day = ''; let pv = 0; let vol = 0;
  for (const b of bars) {
    const { day: d, dm } = cmeClock(b.t);
    if (dm < 930 || dm >= 1320) { out.push(null); continue; }   // 9:30 AM-4 PM New York
    if (d !== day) { day = d; pv = 0; vol = 0; }
    const price = ((b.h + b.l) / 2 + (b.o + b.c) / 2) / 2;
    pv += price * b.v; vol += b.v;
    out.push(vol > 0 ? pv / vol : price);
  }
  return out;
}

type WallKey = keyof Pick<WallSnap, 'outerCall' | 'call' | 'flip' | 'put' | 'outerPut' | 'pin'>;

export function wallSteps(snaps: readonly WallSnap[], key: WallKey, endMs: number): [number, number, number][] {
  const out: [number, number, number][] = [];
  const s = [...snaps].sort((a, b) => a.t - b.t);
  s.forEach((snap, i) => {
    const v = snap[key] ?? null;
    const end = i + 1 < s.length ? s[i + 1].t : Math.max(endMs, snap.t);
    if (v === null) return;
    const last = out[out.length - 1];
    if (last && last[2] === v && last[1] === snap.t) last[1] = end;
    else out.push([snap.t, end, v]);
  });
  return out;
}

export interface GexLevel { price: number; strike: number; gexBn: number }
export interface GexData {
  market: string;
  asOf: string;
  regime: 'positive' | 'negative';
  totalGexBn: number;
  callWall: GexLevel;
  putWall: GexLevel;
  flip: number | null;
  magnets: GexLevel[];
}

const FONT = (w: number, px: number) => `${w} ${px}px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`;
const GREEN = '#2fb67c';
const RED = '#e5534b';
const YELLOW = '#f0b429';
const GREY = 'rgba(170, 178, 190, 0.75)';
const STALE_MS = 20 * 3_600_000;

const bn = (v: number) => `${v >= 0 ? '+' : '−'}$${Math.abs(v).toFixed(1)}B`;
const px = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ES / MES -> ES, NQ / MNQ -> NQ. */
export function gexMarket(symbol: string | null | undefined): 'ES' | 'NQ' | null {
  const s = (symbol ?? '').toUpperCase();
  if (s.startsWith('MES') || s.startsWith('ES')) return 'ES';
  if (s.startsWith('MNQ') || s.startsWith('NQ')) return 'NQ';
  return null;
}

class GexPrimitive implements ISeriesPrimitive<Time> {
  private param: SeriesAttachedParameter<Time> | null = null;
  data: GexData | null = null;
  walls: WallsFile | null = null;
  times: number[] = [];
  bars: VwapBar[] = [];
  barMs = 60_000;
  nowMs = Date.now();
  note = '';

  attached(p: SeriesAttachedParameter<Time>): void { this.param = p; }
  detached(): void { this.param = null; }
  update(): void { this.param?.requestUpdate(); }
  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = { draw: (t) => this.draw(t) };
    return [{ zOrder: () => 'top', renderer: () => renderer }];
  }

  private x(t: number): number | null {
    return this.param?.chart.timeScale().logicalToCoordinate(timeToLogical(this.times, this.barMs, t) as Logical) ?? null;
  }

  /**
   * The STS levels as step lines (each one holds until a refresh moves it), like the OFB GEX study:
   * 1 outer call wall, 2 inner call wall, 3 hedge flip, 4 inner put wall, 5 outer put wall,
   * 6 daily pin (bright after 1 PM ET), 7 VWAP from the 9:30 open, 8 regime strip at the bottom.
   */
  private drawWalls(ctx: CanvasRenderingContext2D, W: number, H: number, labels: [number, string, string][]): void {
    const p = this.param; const wf = this.walls;
    if (!p || !wf) return;
    const spec: [WallKey, string, number, number[], string][] = [
      ['outerCall', '#2f8f3a', 1.3, [6, 3], '1 Outer call wall'],
      ['call', '#43d15a', 2.6, [], '2 Inner call wall'],
      ['flip', '#f2f2f2', 1.6, [], '3 Hedge flip'],
      ['put', '#d23a3a', 2.6, [], '4 Inner put wall'],
      ['outerPut', '#8f2525', 1.3, [6, 3], '5 Outer put wall'],
      ['pin', '#c9a2ff', 2.2, [5, 4], '6 Daily pin'],
    ];
    const days = Object.keys(wf.days).sort();
    const lastBar = this.times.length ? this.times[this.times.length - 1] + this.barMs : this.nowMs;
    const dayEnd = (snaps: WallSnap[]) => { const t = snaps[snaps.length - 1].t; return t + Math.max(0, 1320 - cmeClock(t).dm) * 60_000; };
    for (const [key, color, width, dash, name] of spec) {
      days.forEach((day, di) => {
        const snaps = wf.days[day];
        const isLast = di === days.length - 1;
        const end = Math.min(dayEnd(snaps), isLast ? Math.min(this.nowMs, lastBar) : Infinity);
        const steps = wallSteps(snaps, key, end);
        for (const [a, b, v] of steps) {
          const x0 = this.x(a); const x1 = this.x(b); const y = p.series.priceToCoordinate(v);
          if (x0 === null || x1 === null || y === null) continue;
          if (key === 'pin') {
            // the pin pulls hardest after 1 PM New York (10 AM PT): faint before, bright after
            const split = a + Math.max(0, 1140 - cmeClock(a).dm) * 60_000;
            const xs = Math.min(x1, Math.max(x0, this.x(split) ?? x1));
            ctx.setLineDash(dash); ctx.lineWidth = 1.2; ctx.strokeStyle = 'rgba(201, 162, 255, 0.4)';
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(xs, y); ctx.stroke();
            ctx.lineWidth = width; ctx.strokeStyle = color;
            ctx.beginPath(); ctx.moveTo(xs, y); ctx.lineTo(x1, y); ctx.stroke();
            ctx.setLineDash([]);
            continue;
          }
          ctx.setLineDash(dash); ctx.lineWidth = width; ctx.strokeStyle = color;
          ctx.beginPath();
          ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
          ctx.setLineDash([]);
        }
        // the vertical steps between refreshes
        ctx.setLineDash(dash); ctx.lineWidth = Math.max(1, width - 0.8); ctx.strokeStyle = color;
        for (let i = 1; i < steps.length; i++) {
          if (key === 'pin' || steps[i][0] !== steps[i - 1][1]) continue;
          const x = this.x(steps[i][0]); const y0 = p.series.priceToCoordinate(steps[i - 1][2]); const y1 = p.series.priceToCoordinate(steps[i][2]);
          if (x === null || y0 === null || y1 === null) continue;
          ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
        }
        ctx.setLineDash([]);
        if (isLast && steps.length) {
          const v = steps[steps.length - 1][2]; const y = p.series.priceToCoordinate(v);
          if (y !== null) labels.push([y, `${name}  ${px(v)}`, key === 'outerCall' ? '#5fbf6a' : key === 'outerPut' ? '#d06060' : color]);
        }
      });
    }

    // 7. VWAP from the 9:30 New York open (ama formula)
    const vw = rthVwap(this.bars);
    ctx.strokeStyle = '#e8e36a'; ctx.lineWidth = 1.6; ctx.beginPath();
    let on = false; let lastV: number | null = null;
    this.bars.forEach((b, i) => {
      const v = vw[i];
      const x = this.x(b.t); const y = v === null ? null : p.series.priceToCoordinate(v);
      if (v === null || x === null || y === null) { on = false; return; }
      if (on) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      on = true; lastV = v;
    });
    ctx.stroke();
    if (lastV !== null) { const y = p.series.priceToCoordinate(lastV); if (y !== null) labels.push([y, `7 VWAP (9:30 ET)  ${px(lastV)}`, '#e8e36a']); }

    // 8. regime strip: green = price above the flip (positive gamma), red = below (negative gamma)
    const flipAt = (t: number): number | null => {
      const day = cmeClock(t).day; const snaps = wf.days[day] ?? [];
      let f: number | null = null;
      for (const sn of snaps) if (sn.t <= t) f = sn.flip ?? null;
      return f;
    };
    const bw = Math.max(1, (this.x(this.barMs) ?? 1) - (this.x(0) ?? 0));
    this.bars.forEach((b) => {
      const f = flipAt(b.t);
      if (f === null) return;
      const x = this.x(b.t);
      if (x === null || x < 0 || x > W) return;
      ctx.fillStyle = b.c >= f ? 'rgba(31, 140, 70, 0.85)' : 'rgba(170, 40, 40, 0.85)';
      ctx.fillRect(x, H - 8, Math.max(1, bw), 6);
    });
  }

  private draw(target: CanvasRenderingTarget2D): void {
    const p = this.param;
    if (!p) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width;
      const d = this.data;
      const labels: [number, string, string][] = [];
      const line = (price: number | null, color: string, width: number, dash: number[], label: string) => {
        if (price === null) return;
        const y = p.series.priceToCoordinate(price);
        if (y === null) return;
        ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash);
        ctx.beginPath(); ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(W, Math.round(y) + 0.5); ctx.stroke(); ctx.setLineDash([]);
        labels.push([y, label, color]);
      };
      if (this.walls) this.drawWalls(ctx, W, mediaSize.height, labels);
      if (d) {
        for (const m of d.magnets) line(m.price, GREY, 1, [2, 4], `GEX ${px(m.price)} ${bn(m.gexBn)}`);
        line(d.putWall.price, RED, 2, [], `Put wall ${px(d.putWall.price)} ${bn(d.putWall.gexBn)}`);
        line(d.callWall.price, GREEN, 2, [], `Call wall ${px(d.callWall.price)} ${bn(d.callWall.gexBn)}`);
        line(d.flip, YELLOW, 1.5, [8, 5], `Gamma flip ${d.flip === null ? '' : px(d.flip)}: above = rubber band, below = gas pedal`);
      }
      // labels nudged apart: STS view on the right by the price scale (like the OFB study), gamma view on the left
      labels.sort((a, b) => a[0] - b[0]);
      let last = -99;
      const right = !!this.walls;
      ctx.font = FONT(600, 11); ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      for (const [y, text, color] of labels) {
        const ty = Math.max(y - 2, last + 13); last = ty;
        const tw = ctx.measureText(text).width; const x = right ? W - tw - 10 : 48;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.8)'; ctx.fillRect(x - 4, ty - 12, tw + 8, 13);
        ctx.fillStyle = color; ctx.fillText(text, x, ty);
      }
      // the badge: which mood the dealers put the market in
      const wl = this.walls?.latest;
      const badge = this.note || (wl ? `STS levels from ${wl.etf} (${wl.expirations.length > 1 ? '0DTE + Friday' : wl.expirations[0] ?? ''})${wl.regime === 'positive' ? ' · above flip: positive gamma, range day, walls tend to hold' : wl.regime === 'negative' ? ' · below flip: negative gamma, trend day, walls can break' : ''}` : '') || (d ? (d.regime === 'positive'
        ? `GEX: positive gamma (${bn(d.totalGexBn)}): rubber band, moves get pulled back`
        : `GEX: negative gamma (${bn(d.totalGexBn)}): gas pedal, moves can run`) : '');
      if (!badge) return;
      const stamp = wl ? wl.t : d ? Date.parse(d.asOf) : 0;
      const when = stamp && !this.note ? ` · ${new Date(stamp).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles' })} PT` : '';
      void stamp;
      const text = badge + when;
      ctx.font = FONT(700, 12);
      const w = ctx.measureText(text).width + 14;
      const color = this.note ? GREY : wl ? YELLOW : d?.regime === 'positive' ? GREEN : RED;
      ctx.fillStyle = 'rgba(19, 23, 34, 0.9)'; ctx.fillRect(W - w - 8, 8, w, 22);
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.strokeRect(W - w - 7.5, 8.5, w - 1, 21);
      ctx.fillStyle = color; ctx.textBaseline = 'middle'; ctx.fillText(text, W - w - 1, 19.5);
    });
  }
}

/**
 * GEX levels on the chart: call wall, put wall, gamma flip and the biggest strikes, from the file
 * scripts/gex.py writes (frontend/public/gex/ES.json / NQ.json). Re-reads it every minute.
 */
export class GexLink {
  private readonly prim = new GexPrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private stop: WatchStopHandle | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly host: { getSeries(): ManagedSeriesApi | null; symbol(): string | null; times(): number[]; barMs(): number; bars?(): VwapBar[] }) {
    const store = useGexStore();
    this.stop = watch(() => [store.visible, store.mode] as const, () => { this.syncSeries(); void this.load(); });
    this.timer = setInterval(() => { void this.load(); }, 60_000);
    void this.load();
  }

  syncSeries(): void {
    const store = useGexStore();
    const series = store.visible ? this.host.getSeries() : null;
    if (series === this.attachedTo) return;
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* gone */ }
    this.attachedTo = series;
    series?.attachPrimitive?.(this.prim);
    this.prim.update();
  }

  reattach(): void {
    const series = this.attachedTo;
    if (!series) return;
    try { series.detachPrimitive(this.prim); } catch { /* not attached */ }
    series.attachPrimitive?.(this.prim);
  }

  /** Symbol changed: load that market's file. */
  refresh(): void { void this.load(); }

  /** New candles: keep the step lines lined up with the bars. */
  redraw(): void {
    if (!useGexStore().visible) return;
    this.prim.bars = this.host.bars?.() ?? [];
    this.prim.times = this.host.times(); this.prim.barMs = this.host.barMs(); this.prim.nowMs = Date.now();
    this.prim.update();
  }

  private async load(): Promise<void> {
    if (!useGexStore().visible) return;
    if (this.attachedTo !== this.host.getSeries()) this.syncSeries();
    const market = gexMarket(this.host.symbol());
    this.prim.bars = this.host.bars?.() ?? [];
    if (!market) { this.prim.data = null; this.prim.note = 'GEX: only for ES / NQ'; this.prim.update(); return; }
    this.prim.times = this.host.times(); this.prim.barMs = this.host.barMs(); this.prim.nowMs = Date.now();
    if (useGexStore().mode === 'walls') {
      this.prim.data = null;
      try {
        const res = await fetch(`/gex/walls_${market}.json?t=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(String(res.status));
        const wf = (await res.json()) as WallsFile;
        this.prim.walls = wf;
        this.prim.note = Date.now() - wf.latest.t > STALE_MS ? 'Option walls are old: run oi-walls.bat' : '';
      } catch {
        this.prim.walls = null;
        this.prim.note = 'Option walls: none yet. Run scripts\\windows\\oi-walls.bat';
      }
      this.prim.update();
      return;
    }
    this.prim.walls = null;
    try {
      const res = await fetch(`/gex/${market}.json?t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as GexData;
      this.prim.data = data;
      this.prim.note = Date.now() - Date.parse(data.asOf) > STALE_MS ? 'GEX: levels are old, run gex.bat' : '';
    } catch {
      this.prim.data = null;
      this.prim.note = 'GEX: no levels yet. Run scripts\\windows\\gex.bat';
    }
    this.prim.update();
  }

  destroy(): void {
    this.stop?.();
    if (this.timer) clearInterval(this.timer);
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* gone */ }
    this.attachedTo = null;
  }
}
