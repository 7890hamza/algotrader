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

import { buildBoard, isCarried, levelOdds, levelStatus, type DayPlan, type PlanLevel } from './gamePlan';

const FONT = '500 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const UP = '#2fb67c';
const EMPTY: readonly IPrimitivePaneView[] = [];
const LABEL_GAP = 13;

const crisp = (v: number): number => Math.round(v) + 0.5;

interface Line {
  y: number;
  x0: number;
  x1: number;
  color: string;
  dashed: boolean;
  faded: boolean;
  hitX: number | null;
  label: string | null;
}

const STUB_PX = 36;

/** What goes on the chart: the same nearby open targets the panel lists, and today's hits. */
export function chartLevels(plan: DayPlan, t: number, price: number): PlanLevel[] {
  const board = buildBoard(plan, t, price);
  // only the most recent hits, so the chart stays readable
  return [...board.above, ...board.below, ...board.done.slice(0, 8)].map((r) => r.level);
}

class GamePlanRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly lines: readonly Line[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      for (const l of this.lines) {
        ctx.globalAlpha = l.faded ? 0.45 : l.dashed ? 0.75 : 1;
        ctx.strokeStyle = l.color;
        ctx.lineWidth = 1;
        ctx.setLineDash(l.dashed ? [5, 4] : []);
        ctx.beginPath();
        ctx.moveTo(l.x0, crisp(l.y));
        ctx.lineTo(l.x1, crisp(l.y));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
        if (l.hitX !== null) {
          ctx.fillStyle = UP;
          ctx.beginPath();
          ctx.arc(l.hitX, l.y, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = '#131722';
          ctx.font = '700 8px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('✓', l.hitX, l.y + 0.5);
        }
      }
      // Labels at the right edge for open targets, spread so they never sit on top of each other.
      const labels = this.lines.filter((l) => l.label).map((l) => ({ y: l.y, l })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < LABEL_GAP) labels[i].y = labels[i - 1].y + LABEL_GAP;
      ctx.font = FONT;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (const { y, l } of labels) {
        const w = ctx.measureText(l.label!).width;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.85)';
        ctx.fillRect(mediaSize.width - w - 12, y - 7, w + 8, 14);
        ctx.fillStyle = l.color;
        ctx.globalAlpha = l.dashed ? 0.85 : 1;
        ctx.fillText(l.label!, mediaSize.width - 8, y);
        ctx.globalAlpha = 1;
      }
      ctx.restore();
    });
  }
}

class GamePlanPaneView implements IPrimitivePaneView {
  constructor(private readonly primitive: GamePlanPrimitive) {}

  zOrder(): PrimitivePaneViewZOrder {
    return 'normal';
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.primitive.createRenderer();
  }
}

/** Draws the Game Plan's targets on the price series: ↻ dashed when carried, ✓ where hit. */
export class GamePlanPrimitive implements ISeriesPrimitive<Time> {
  private params: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private plan: DayPlan | null = null;
  private t = 0;
  private price = 0;
  private readonly views: readonly IPrimitivePaneView[] = [new GamePlanPaneView(this)];

  set(plan: DayPlan | null, t: number, price = 0): void {
    this.plan = plan;
    this.t = t;
    this.price = price || plan?.last?.close || 0;
    this.params?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.params = param;
  }

  detached(): void {
    this.params = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.plan ? this.views : EMPTY;
  }

  private x(ms: number): number | null {
    const ts = this.params?.chart.timeScale();
    if (!ts) return null;
    const time = Math.floor(ms / 1000) as Time;
    const exact = ts.timeToCoordinate(time);
    if (exact !== null) return Number(exact);
    const idx = ts.timeToIndex(time, true);
    if (idx === null) return null;
    const c = ts.logicalToCoordinate(idx as unknown as Logical);
    return c === null ? null : Number(c);
  }

  createRenderer(): IPrimitivePaneRenderer | null {
    const plan = this.plan;
    const series = this.params?.series;
    const width = this.params?.chart.timeScale().width() ?? 0;
    if (!plan || !series) return null;
    const lines: Line[] = [];
    for (const l of chartLevels(plan, this.t, this.price)) {
      const y = series.priceToCoordinate(l.price);
      if (y === null) continue;
      const st = levelStatus(l, this.t);
      const carried = isCarried(l, this.t);
      const hitX = st === 'done' && l.hitAt !== null ? this.x(l.hitAt) : null;
      if (st === 'done' && hitX === null) continue;
      // Open lines start where their own window starts (or where the carry began); hits are a short stub.
      const from = carried && !l.fromDay ? Math.max(l.frm, l.origUntil) : l.frm;
      const x0 = st === 'done' ? Math.max(0, hitX! - STUB_PX) : Math.max(0, this.x(from) ?? 0);
      const odds = levelOdds(l, this.t, plan);
      const label = st === 'open'
        ? `${carried ? '↻ ' : ''}${l.label}${odds.value !== null ? `  ${odds.value}%` : ''}`
        : null;
      lines.push({
        y: Number(y),
        x0,
        x1: st === 'done' ? (hitX ?? x0) : width,
        color: l.color,
        dashed: carried || l.kind === 'hour_open',
        faded: st === 'done',
        hitX,
        label,
      });
    }
    return lines.length ? new GamePlanRenderer(lines) : null;
  }
}
