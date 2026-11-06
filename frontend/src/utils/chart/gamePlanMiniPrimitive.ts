import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  Logical,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

import { isCarried, type DayPlan, type PlanLevel } from './gamePlan';

const FONT = '11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const UP = '#2fb67c';
const RTH = 'rgba(76, 155, 232, 0.07)';
const STUB_PX = 52;
const HOUR = 3_600_000;
/** Room kept at the bottom of the pane for the time marks. */
export const AXIS_PX = 20;
const crisp = (v: number): number => Math.round(v) + 0.5;

/** Shorter names for the small chart. */
export const miniName = (label: string): string =>
  label.replace(/ extension$/, '').replace(/^Yesterday's /, 'Yday ').replace(/ \((pETH|pRTH)\)$/, '');

export interface MiniOpen { level: PlanLevel; odds: number | null }
export interface MiniScene {
  plan: DayPlan;
  t: number;
  open: MiniOpen[];
  hits: PlanLevel[];
  /** Added to epoch ms before it becomes a chart time (the chart shows Pacific time). */
  shiftMs: number;
}

interface Drawn {
  band: [number, number] | null;
  ticks: { x: number; text: string }[];
  lines: { y: number; x0: number; x1: number; color: string; dashed: boolean }[];
  dots: { x: number; y: number }[];
  labels: { x: number; y: number; text: string; color: string; align: CanvasTextAlign }[];
}

class BandRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly d: Drawn) {}
  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (this.d.band) {
        ctx.fillStyle = RTH;
        ctx.fillRect(this.d.band[0], 0, this.d.band[1] - this.d.band[0], mediaSize.height - AXIS_PX);
      }
      // Our own time marks (3 AM, 6:30, 10 AM, 1 PM ...) along the bottom.
      ctx.font = FONT;
      ctx.fillStyle = '#8a919c';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      let last = -1e9;
      for (const tk of this.d.ticks) {
        if (tk.x < 16 || tk.x > mediaSize.width - 16 || tk.x - last < 36) continue;
        ctx.fillText(tk.text, tk.x, mediaSize.height - 5);
        last = tk.x;
      }
    });
  }
}

class LinesRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly d: Drawn) {}
  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      for (const l of this.d.lines) {
        ctx.strokeStyle = l.color;
        ctx.lineWidth = l.dashed ? 1 : 1.2;
        ctx.globalAlpha = l.dashed ? 0.8 : 1;
        ctx.setLineDash(l.dashed ? [5, 4] : []);
        ctx.beginPath();
        ctx.moveTo(l.x0, crisp(l.y));
        ctx.lineTo(l.x1, crisp(l.y));
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
      for (const p of this.d.dots) {
        ctx.fillStyle = UP;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
      // Names just above their line; a name that would sit on another one is skipped.
      ctx.font = FONT;
      ctx.textBaseline = 'bottom';
      const placed: { x0: number; x1: number; y: number }[] = [];
      for (const lb of [...this.d.labels].sort((a, b) => a.y - b.y)) {
        const w = ctx.measureText(lb.text).width;
        let x = lb.x;
        if (lb.align === 'center') x = Math.min(mediaSize.width - w / 2 - 2, Math.max(w / 2 + 2, x));
        const x0 = lb.align === 'right' ? x - w : lb.align === 'center' ? x - w / 2 : x;
        const y = lb.y - 3;
        if (y < 12 || placed.some((p) => Math.abs(p.y - y) < 12 && x0 < p.x1 && x0 + w > p.x0)) continue;
        placed.push({ x0, x1: x0 + w, y });
        ctx.fillStyle = lb.color;
        ctx.textAlign = lb.align;
        ctx.fillText(lb.text, x, y);
      }
      ctx.restore();
    });
  }
}

class View implements IPrimitivePaneView {
  constructor(private readonly p: GamePlanMiniPrimitive, private readonly part: 'band' | 'lines') {}
  zOrder(): PrimitivePaneViewZOrder {
    return this.part === 'band' ? 'bottom' : 'normal';
  }
  renderer(): IPrimitivePaneRenderer | null {
    const d = this.p.layout();
    if (!d) return null;
    if (this.part === 'band') return new BandRenderer(d);
    return new LinesRenderer(d);
  }
}

/**
 * The Game Plan mini chart's drawings, in the mockup's style: the RTH window shaded, open
 * targets as lines with their name above (dashed with ↻ when carried), and each recent hit as a
 * short line ending in a green dot.
 */
export class GamePlanMiniPrimitive implements ISeriesPrimitive<Time> {
  private params: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private scene: MiniScene | null = null;
  private readonly views: readonly IPrimitivePaneView[] = [new View(this, 'band'), new View(this, 'lines')];

  set(scene: MiniScene | null): void {
    this.scene = scene;
    this.params?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.params = param;
  }

  detached(): void {
    this.params = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  private x(ms: number): number | null {
    const ts = this.params?.chart.timeScale();
    if (!ts || !this.scene) return null;
    const time = Math.floor((ms + this.scene.shiftMs) / 1000) as Time;
    const exact = ts.timeToCoordinate(time);
    if (exact !== null) return Number(exact);
    const idx = ts.timeToIndex(time, true);
    if (idx === null) return null;
    const c = ts.logicalToCoordinate(idx as unknown as Logical);
    return c === null ? null : Number(c);
  }

  layout(): Drawn | null {
    const s = this.scene;
    const series = this.params?.series;
    if (!s || !series) return null;
    // the pane's width (the time scale reports 0 while it's hidden)
    const width = this.params!.chart.paneSize().width;
    const d: Drawn = { band: null, ticks: [], lines: [], dots: [], labels: [] };
    const mid = s.plan.start + 9 * HOUR; // midnight Pacific
    for (const [ms, text] of [[s.plan.start + 3 * HOUR, '6 PM'], [mid, '12 AM'], [mid + 3 * HOUR, '3 AM'], [s.plan.ctx.rth0, '6:30'], [mid + 10 * HOUR, '10 AM'], [s.plan.ctx.rth1, '1 PM']] as const) {
      const x = this.x(ms);
      if (x !== null) d.ticks.push({ x, text });
    }
    const b0 = this.x(s.plan.ctx.rth0);
    const b1 = this.x(s.plan.ctx.rth1);
    if (b0 !== null && b1 !== null && b1 > b0) d.band = [b0, b1];
    for (const { level: l, odds } of s.open) {
      const y = series.priceToCoordinate(l.price);
      if (y === null) continue;
      const carried = isCarried(l, s.t);
      const x0 = Math.min(Math.max(0, this.x(l.frm) ?? 0), width - 40);
      d.lines.push({ y: Number(y), x0, x1: width, color: l.color, dashed: carried || l.kind === 'hour_open' });
      d.labels.push({ x: width - 4, y: Number(y), text: `${carried ? '↻ ' : ''}${miniName(l.label)}${odds !== null ? ` · ${Math.round(odds)}%` : ''}`, color: l.color, align: 'right' });
    }
    for (const l of s.hits) {
      if (l.hitAt === null) continue;
      const y = series.priceToCoordinate(l.price);
      const hx = this.x(l.hitAt);
      if (y === null || hx === null) continue;
      const x0 = Math.max(0, hx - STUB_PX);
      d.lines.push({ y: Number(y), x0, x1: hx, color: l.color, dashed: false });
      d.dots.push({ x: hx, y: Number(y) });
      d.labels.push({ x: (x0 + hx) / 2, y: Number(y), text: miniName(l.label), color: l.color, align: 'center' });
    }
    return d;
  }
}
