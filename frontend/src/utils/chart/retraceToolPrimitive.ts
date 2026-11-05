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

import { buildRetraceModel, formatPct, type RetraceAnchor, type RetraceDrawing } from './retraceTool';

const FONT = '500 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const BOLD = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const UP = '#2fb67c';
const DOWN = '#e5534b';
const HANDLE = 5;
const EMPTY: readonly IPrimitivePaneView[] = [];

const crisp = (v: number): number => Math.round(v) + 0.5;
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export type RetraceHit = { id: string; part: 'a' | 'b' | 'close' | 'body' };

interface Drawn {
  d: RetraceDrawing;
  ax: number;
  ay: number;
  bx: number;
  by: number;
  x0: number;
  x1: number;
  selected: boolean;
  rows: { y: number; text: string; edge: boolean }[];
  zoneTop: number;
  zoneBottom: number;
  legTop: number;
  legBottom: number;
  up: boolean;
}

class RetraceRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly drawn: readonly Drawn[], private readonly pending: { x: number; y: number; cx: number | null; cy: number | null } | null) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.save();
      for (const r of this.drawn) {
        const color = r.up ? UP : DOWN;
        ctx.fillStyle = 'rgba(138, 145, 156, 0.10)';
        ctx.fillRect(r.x0, r.legTop, r.x1 - r.x0, r.legBottom - r.legTop);
        ctx.fillStyle = r.up ? 'rgba(47, 182, 124, 0.30)' : 'rgba(229, 83, 75, 0.30)';
        ctx.fillRect(r.x0, r.zoneTop, r.x1 - r.x0, r.zoneBottom - r.zoneTop);
        ctx.font = FONT;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        let lastY = -1e9;
        for (const row of [...r.rows].sort((p, q) => p.y - q.y)) {
          ctx.strokeStyle = row.edge ? color : 'rgba(138, 145, 156, 0.6)';
          ctx.lineWidth = 1;
          ctx.setLineDash(row.edge ? [] : [3, 3]);
          ctx.beginPath();
          ctx.moveTo(r.x0, crisp(row.y));
          ctx.lineTo(r.x1, crisp(row.y));
          ctx.stroke();
          ctx.setLineDash([]);
          const ty = Math.max(row.y - 7, lastY + 12);
          lastY = ty;
          ctx.font = row.edge ? BOLD : FONT;
          ctx.fillStyle = row.edge ? color : '#9aa4b2';
          ctx.fillText(row.text, r.x1 - 4, ty);
        }
        ctx.strokeStyle = 'rgba(233, 196, 106, 0.9)';
        ctx.lineWidth = 1.3;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(r.ax, r.ay);
        ctx.lineTo(r.bx, r.by);
        ctx.stroke();
        ctx.setLineDash([]);
        for (const [x, y] of [[r.ax, r.ay], [r.bx, r.by]] as const) {
          ctx.fillStyle = r.selected ? '#e9c46a' : '#131722';
          ctx.strokeStyle = '#e9c46a';
          ctx.lineWidth = 1.5;
          ctx.fillRect(x - HANDLE, y - HANDLE, HANDLE * 2, HANDLE * 2);
          ctx.strokeRect(x - HANDLE + 0.5, y - HANDLE + 0.5, HANDLE * 2 - 1, HANDLE * 2 - 1);
        }
        if (r.selected) {
          const cx = r.bx + 10;
          const cy = r.by - 22;
          ctx.fillStyle = 'rgba(19, 23, 34, 0.9)';
          ctx.fillRect(cx, cy, 16, 16);
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
          ctx.lineWidth = 1;
          ctx.strokeRect(cx + 0.5, cy + 0.5, 15, 15);
          ctx.strokeStyle = '#e6e6e6';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(cx + 4.5, cy + 4.5);
          ctx.lineTo(cx + 11.5, cy + 11.5);
          ctx.moveTo(cx + 11.5, cy + 4.5);
          ctx.lineTo(cx + 4.5, cy + 11.5);
          ctx.stroke();
        }
      }
      if (this.pending) {
        const { x, y, cx, cy } = this.pending;
        if (cx !== null && cy !== null) {
          ctx.strokeStyle = 'rgba(233, 196, 106, 0.9)';
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(cx, cy);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        ctx.fillStyle = '#e9c46a';
        ctx.fillRect(x - HANDLE, y - HANDLE, HANDLE * 2, HANDLE * 2);
        ctx.font = BOLD;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText('Click the second anchor', x + 10, y - 6);
      }
      ctx.restore();
    });
  }
}

class RetracePaneView implements IPrimitivePaneView {
  constructor(private readonly primitive: RetraceToolPrimitive) {}

  zOrder(): PrimitivePaneViewZOrder {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.primitive.createRenderer();
  }
}

/** Draws every Retrace drawing on the price series; also answers what is under a point. */
export class RetraceToolPrimitive implements ISeriesPrimitive<Time> {
  private params: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private drawings: RetraceDrawing[] = [];
  private selectedId: string | null = null;
  private pending: RetraceAnchor | null = null;
  private cursor: { x: number; y: number } | null = null;
  private readonly views: readonly IPrimitivePaneView[] = [new RetracePaneView(this)];

  set(drawings: readonly RetraceDrawing[], selectedId: string | null, pending: RetraceAnchor | null, cursor: { x: number; y: number } | null): void {
    this.drawings = [...drawings];
    this.selectedId = selectedId;
    this.pending = pending;
    this.cursor = cursor;
    this.params?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.params = param;
  }

  detached(): void {
    this.params = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.drawings.length || this.pending ? this.views : EMPTY;
  }

  private x(time: number): number | null {
    const ts = this.params?.chart.timeScale();
    if (!ts) return null;
    const exact = ts.timeToCoordinate(time as Time);
    if (exact !== null) return Number(exact);
    const idx = ts.timeToIndex(time as Time, true);
    if (idx === null) return null;
    const c = ts.logicalToCoordinate(idx as unknown as Logical);
    return c === null ? null : Number(c);
  }

  private y(price: number): number | null {
    const v = this.params?.series.priceToCoordinate(price);
    return v === null || v === undefined ? null : Number(v);
  }

  private layout(): Drawn[] {
    const out: Drawn[] = [];
    const width = this.params?.chart.timeScale().width() ?? 0;
    for (const d of this.drawings) {
      const ax = this.x(d.a.time);
      const bx = this.x(d.b.time);
      const ay = this.y(d.a.price);
      const by = this.y(d.b.price);
      if (ax === null || bx === null || ay === null || by === null) continue;
      const m = buildRetraceModel(d);
      const zt = this.y(m.zoneHigh);
      const zb = this.y(m.zoneLow);
      const lt = this.y(Math.max(d.a.price, d.b.price));
      const lb = this.y(Math.min(d.a.price, d.b.price));
      if (zt === null || zb === null || lt === null || lb === null) continue;
      const x0 = Math.min(ax, bx);
      // The zone reaches out to the right of the leg (to the pane edge) so price can come back to it.
      const x1 = Math.max(Math.max(ax, bx) + 60, width - 4);
      const rows = m.levels
        .map((l) => ({ y: this.y(l.price), text: `${formatPct(l.pct)}  ${fmt(l.price)}`, edge: l.edge }))
        .filter((r): r is { y: number; text: string; edge: boolean } => r.y !== null);
      out.push({ d, ax, ay, bx, by, x0, x1, selected: d.id === this.selectedId, rows, zoneTop: zt, zoneBottom: zb, legTop: lt, legBottom: lb, up: m.up });
    }
    return out;
  }

  createRenderer(): IPrimitivePaneRenderer | null {
    const drawn = this.layout();
    let pending: { x: number; y: number; cx: number | null; cy: number | null } | null = null;
    if (this.pending) {
      const x = this.x(this.pending.time);
      const y = this.y(this.pending.price);
      if (x !== null && y !== null) pending = { x, y, cx: this.cursor?.x ?? null, cy: this.cursor?.y ?? null };
    }
    return drawn.length || pending ? new RetraceRenderer(drawn, pending) : null;
  }

  /** The anchor, remove button or zone under (x, y), newest drawing first. */
  hit(x: number, y: number): RetraceHit | null {
    const drawn = this.layout().reverse();
    for (const r of drawn) {
      if (r.selected && x >= r.bx + 8 && x <= r.bx + 28 && y >= r.by - 24 && y <= r.by - 4) return { id: r.d.id, part: 'close' };
      if (Math.abs(x - r.ax) <= HANDLE + 3 && Math.abs(y - r.ay) <= HANDLE + 3) return { id: r.d.id, part: 'a' };
      if (Math.abs(x - r.bx) <= HANDLE + 3 && Math.abs(y - r.by) <= HANDLE + 3) return { id: r.d.id, part: 'b' };
    }
    for (const r of drawn) {
      if (x >= r.x0 && x <= r.x1 && y >= r.legTop && y <= r.legBottom) return { id: r.d.id, part: 'body' };
    }
    return null;
  }
}
