import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

import type { PositionHandle, PositionModel, PositionToolState } from './positionTool';

const FONT = '500 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const BOLD = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const HIT_PX = 6;
const EMPTY: readonly IPrimitivePaneView[] = [];

const crisp = (v: number): number => Math.round(v) + 0.5;

interface Drawn {
  x0: number;
  rows: { key: string; y: number; color: string; dashed: boolean; label: string }[];
  entryY: number;
  stopY: number;
  targetY: number;
  valid: boolean;
}

class PositionRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly d: Drawn) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const { x0, entryY, stopY, targetY, valid } = this.d;
      const x1 = mediaSize.width - 2;
      if (x1 <= x0) return;
      ctx.save();
      if (valid) {
        ctx.fillStyle = 'rgba(224, 87, 74, 0.13)';
        ctx.fillRect(x0, Math.min(entryY, stopY), x1 - x0, Math.abs(stopY - entryY));
        ctx.fillStyle = 'rgba(63, 185, 80, 0.12)';
        ctx.fillRect(x0, Math.min(entryY, targetY), x1 - x0, Math.abs(targetY - entryY));
      }
      for (const row of this.d.rows) {
        const main = row.key !== 'ladder';
        ctx.strokeStyle = valid ? row.color : '#8a919c';
        ctx.lineWidth = main ? 1.5 : 1;
        ctx.setLineDash(row.dashed ? [3, 4] : []);
        ctx.beginPath();
        ctx.moveTo(x0, crisp(row.y));
        ctx.lineTo(x1, crisp(row.y));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = main ? BOLD : FONT;
        ctx.fillStyle = valid ? row.color : '#8a919c';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(row.label, x1 - 4, row.y - 3);
        if (main) {
          // Drag handle at the left end of each main line.
          ctx.fillStyle = row.color;
          ctx.fillRect(x0 - 4, row.y - 4, 8, 8);
          ctx.strokeStyle = '#131722';
          ctx.lineWidth = 1;
          ctx.strokeRect(x0 - 4 + 0.5, row.y - 4 + 0.5, 7, 7);
        }
      }
      // Remove button on the entry line, just right of its drag handle.
      const cx = x0 + 10;
      const cy = entryY - 8;
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
      if (!valid) {
        ctx.font = BOLD;
        ctx.fillStyle = '#E0574A';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('Stop and target must be on opposite sides of the entry', x0 + 8, Math.min(entryY, stopY, targetY) + 4);
      }
      ctx.restore();
    });
  }
}

class PositionPaneView implements IPrimitivePaneView {
  constructor(private readonly primitive: PositionToolPrimitive) {}

  zOrder(): PrimitivePaneViewZOrder {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.primitive.createRenderer();
  }
}

/** Draws a risk-to-reward plan (zones, lines, R ladder, labels) on the price series. */
export class PositionToolPrimitive implements ISeriesPrimitive<Time> {
  private params: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private state: PositionToolState | null = null;
  private model: PositionModel | null = null;
  private readonly views: readonly IPrimitivePaneView[] = [new PositionPaneView(this)];

  set(state: PositionToolState | null, model: PositionModel | null): void {
    this.state = state;
    this.model = model;
    this.params?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.params = param;
  }

  detached(): void {
    this.params = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.state && this.model ? this.views : EMPTY;
  }

  private y(price: number): number | null {
    const v = this.params?.series.priceToCoordinate(price);
    return v === null || v === undefined ? null : Number(v);
  }

  private x0(): number | null {
    const ts = this.params?.chart.timeScale();
    if (!ts || !this.state) return null;
    const exact = ts.timeToCoordinate(this.state.time as Time);
    if (exact !== null) return Number(exact);
    const idx = ts.timeToIndex(this.state.time as Time, true);
    if (idx === null) return null;
    const c = ts.logicalToCoordinate(idx as never);
    return c === null ? null : Number(c);
  }

  createRenderer(): IPrimitivePaneRenderer | null {
    const s = this.state;
    const m = this.model;
    if (!s || !m) return null;
    const x0 = this.x0();
    const entryY = this.y(s.entry);
    const stopY = this.y(s.stop);
    const targetY = this.y(s.target);
    if (x0 === null || entryY === null || stopY === null || targetY === null) return null;
    const rows: Drawn['rows'] = [];
    for (const l of m.lines) {
      const y = this.y(l.price);
      if (y !== null) rows.push({ key: l.key, y, color: l.color, dashed: l.dashed, label: l.label });
    }
    return new PositionRenderer({ x0, rows, entryY, stopY, targetY, valid: m.valid });
  }

  /** True when (x, y) is on the remove button drawn on the entry line. */
  hitClose(x: number, y: number): boolean {
    const x0 = this.x0();
    const ey = this.state ? this.y(this.state.entry) : null;
    if (x0 === null || ey === null) return false;
    return x >= x0 + 8 && x <= x0 + 28 && y >= ey - 10 && y <= ey + 10;
  }

  /** The handle under a pane y coordinate (entry wins ties), if any. */
  hit(y: number): PositionHandle | null {
    const s = this.state;
    if (!s) return null;
    let best: PositionHandle | null = null;
    let bestD = HIT_PX + 1;
    for (const key of ['entry', 'stop', 'target'] as const) {
      const py = this.y(s[key]);
      if (py === null) continue;
      const d = Math.abs(py - y);
      if (d < bestD) {
        best = key;
        bestD = d;
      }
    }
    return bestD <= HIT_PX ? best : null;
  }
}
