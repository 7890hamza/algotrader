import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';
import { watch, type WatchStopHandle } from 'vue';

import { useGexStore } from '@/stores/gexStore';

import type { ManagedSeriesApi } from './ChartManager';

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
  note = '';

  attached(p: SeriesAttachedParameter<Time>): void { this.param = p; }
  detached(): void { this.param = null; }
  update(): void { this.param?.requestUpdate(); }
  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = { draw: (t) => this.draw(t) };
    return [{ zOrder: () => 'top', renderer: () => renderer }];
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
      const badge = this.note || (d ? (d.regime === 'positive'
        ? `GEX: positive gamma (${bn(d.totalGexBn)}): rubber band, moves get pulled back`
        : `GEX: negative gamma (${bn(d.totalGexBn)}): gas pedal, moves can run`) : '');
      if (!badge) return;
      const when = d && !this.note ? ` · ${new Date(d.asOf).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles' })} PT` : '';
      const text = badge + when;
      ctx.font = FONT(700, 12);
      const w = ctx.measureText(text).width + 14;
      const color = this.note ? GREY : d?.regime === 'positive' ? GREEN : RED;
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

  constructor(private readonly host: { getSeries(): ManagedSeriesApi | null; symbol(): string | null }) {
    const store = useGexStore();
    this.stop = watch(() => store.visible, () => { this.syncSeries(); void this.load(); });
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

  private async load(): Promise<void> {
    if (!useGexStore().visible) return;
    if (this.attachedTo !== this.host.getSeries()) this.syncSeries();
    const market = gexMarket(this.host.symbol());
    if (!market) { this.prim.data = null; this.prim.note = 'GEX: only for ES / NQ'; this.prim.update(); return; }
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
