import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, Logical, SeriesAttachedParameter, Time } from 'lightweight-charts';
import { watch, type WatchStopHandle } from 'vue';

import { useGexStore } from '@/stores/gexStore';

import type { ManagedSeriesApi } from './ChartManager';
import { timeToLogical } from './drawings';

/** One refresh of the option walls (scripts/oi_walls.py), already in futures prices. */
export interface WallSnap { t: number; outerCall: number | null; call: number | null; flip: number | null; put: number | null; outerPut: number | null; etf: string; ratio: number; expirations: string[]; zone?: number }
export interface WallsFile { market: string; days: Record<string, WallSnap[]>; latest: WallSnap }

/** Stepped segments for one level: [start ms, end ms, price], one per stretch the level stayed put. */
export function wallSteps(snaps: readonly WallSnap[], key: keyof Pick<WallSnap, 'outerCall' | 'call' | 'flip' | 'put' | 'outerPut'>, endMs: number): [number, number, number][] {
  const out: [number, number, number][] = [];
  const s = [...snaps].sort((a, b) => a.t - b.t);
  s.forEach((snap, i) => {
    const v = snap[key];
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

  /** Step lines like the OFB GEX study: each level holds until a refresh moves it. */
  private drawWalls(ctx: CanvasRenderingContext2D, W: number, labels: [number, string, string][]): void {
    const p = this.param; const wf = this.walls;
    if (!p || !wf) return;
    const spec: [keyof Pick<WallSnap, 'outerCall' | 'call' | 'flip' | 'put' | 'outerPut'>, string, number, number[], string][] = [
      ['outerCall', 'rgba(47, 182, 124, 0.6)', 1.5, [6, 4], 'Outer call wall'],
      ['call', GREEN, 2.5, [], 'Call wall'],
      ['flip', YELLOW, 1.5, [8, 5], 'Flip'],
      ['put', RED, 2.5, [], 'Put wall'],
      ['outerPut', 'rgba(229, 83, 75, 0.6)', 1.5, [6, 4], 'Outer put wall'],
    ];
    const days = Object.keys(wf.days).sort();
    for (const [key, color, width, dash, name] of spec) {
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash);
      days.forEach((day, di) => {
        const snaps = wf.days[day];
        const isLast = di === days.length - 1;
        const lastBar = this.times.length ? this.times[this.times.length - 1] + this.barMs : this.nowMs;
        const end = isLast ? Math.min(this.nowMs, lastBar) : snaps[snaps.length - 1].t + 30 * 60_000;
        const steps = wallSteps(snaps, key, end);
        ctx.beginPath();
        let prevX: number | null = null; let prevY: number | null = null;
        for (const [a, b, v] of steps) {
          const x0 = this.x(a); const x1 = this.x(b); const y = p.series.priceToCoordinate(v);
          if (x0 === null || x1 === null || y === null) { prevX = null; continue; }
          const zone = snaps[snaps.length - 1].zone ?? 0;
          if (zone && (key === 'call' || key === 'put')) {
            // STS: a level is a zone; reactions usually come within 10-20 NQ points of it
            const yt = p.series.priceToCoordinate(v + zone); const yb = p.series.priceToCoordinate(v - zone);
            if (yt !== null && yb !== null) { ctx.save(); ctx.fillStyle = key === 'call' ? 'rgba(47, 182, 124, 0.10)' : 'rgba(229, 83, 75, 0.10)'; ctx.fillRect(x0, yt, x1 - x0, yb - yt); ctx.restore(); }
          }
          if (prevX !== null && prevY !== null && Math.abs(prevX - x0) < 2) ctx.lineTo(x0, y); // the vertical step
          else ctx.moveTo(x0, y);
          ctx.lineTo(x1, y);
          prevX = x1; prevY = y;
        }
        ctx.stroke();
        if (isLast && steps.length) {
          const v = steps[steps.length - 1][2]; const y = p.series.priceToCoordinate(v);
          if (y !== null) labels.push([y, `${name} ${px(v)}`, color.startsWith('rgba') ? (key === 'outerCall' ? GREEN : RED) : color]);
        }
      });
      ctx.setLineDash([]);
    }
    void W;
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
      if (this.walls) this.drawWalls(ctx, W, labels);
      if (d) {
        for (const m of d.magnets) line(m.price, GREY, 1, [2, 4], `GEX ${px(m.price)} ${bn(m.gexBn)}`);
        line(d.putWall.price, RED, 2, [], `Put wall ${px(d.putWall.price)} ${bn(d.putWall.gexBn)}`);
        line(d.callWall.price, GREEN, 2, [], `Call wall ${px(d.callWall.price)} ${bn(d.callWall.gexBn)}`);
        line(d.flip, YELLOW, 1.5, [8, 5], `Gamma flip ${d.flip === null ? '' : px(d.flip)}: above = rubber band, below = gas pedal`);
      }
      // labels on the left so they don't sit on the price scale, nudged apart
      labels.sort((a, b) => a[0] - b[0]);
      let last = -99;
      ctx.font = FONT(600, 11); ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      for (const [y, text, color] of labels) {
        const ty = Math.max(y - 2, last + 13); last = ty;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.75)'; ctx.fillRect(44, ty - 12, ctx.measureText(text).width + 8, 13);
        ctx.fillStyle = color; ctx.fillText(text, 48, ty);
      }
      // the badge: which mood the dealers put the market in
      const wl = this.walls?.latest;
      const badge = this.note || (wl ? `Option walls: ${wl.etf} ${wl.expirations.length > 1 ? '0DTE + Friday' : wl.expirations[0] ?? ''} open interest` : '') || (d ? (d.regime === 'positive'
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

  constructor(private readonly host: { getSeries(): ManagedSeriesApi | null; symbol(): string | null; times(): number[]; barMs(): number }) {
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
    this.prim.times = this.host.times(); this.prim.barMs = this.host.barMs(); this.prim.nowMs = Date.now();
    this.prim.update();
  }

  private async load(): Promise<void> {
    if (!useGexStore().visible) return;
    if (this.attachedTo !== this.host.getSeries()) this.syncSeries();
    const market = gexMarket(this.host.symbol());
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
