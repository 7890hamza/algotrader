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

import { runFades, statRuns, statsAhead, statsLadder, type RunFade, type StatRun } from '../setups';

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

interface RunBox { x0: number; x1: number; y0: number; y1: number; up: boolean; text: string }

/** Heads-up bracket: a column just right of the last candle, from price to the farthest open stat in reach. */
interface AheadBox { x: number; yPrice: number; yFar: number; ys: number[]; up: boolean; text: string }

/** Run fade trade box: like the QuickTrade box - red to the stop, green to the target. */
interface FadeBox { x0: number; x1: number; yEntry: number; yStop: number; yTarget: number; text: string; result: string | null; win: boolean | null }

/** The "I" measuring tool (like the QuickTrade box): a purple bracket between two prices, labelled in points. */
interface Ruler { x: number; ya: number; yb: number; text: string }

const fmtPts = (v: number) => (v >= 10 ? (Math.round(v * 4) / 4).toFixed(2).replace(/\.?0+$/, '') : (Math.round(v * 4) / 4).toString());

function drawRuler(ctx: CanvasRenderingContext2D, r: Ruler, width: number): void {
  ctx.strokeStyle = '#8f87e6'; ctx.lineWidth = 1.5; ctx.setLineDash([]);
  const x = crisp(r.x);
  ctx.beginPath(); ctx.moveTo(x, r.ya); ctx.lineTo(x, r.yb); ctx.stroke();
  for (const y of [r.ya, r.yb]) { ctx.beginPath(); ctx.moveTo(x - 5, crisp(y)); ctx.lineTo(x + 5, crisp(y)); ctx.stroke(); }
  ctx.font = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  const tw = ctx.measureText(r.text).width;
  const ly = (r.ya + r.yb) / 2;
  const lx = r.x + 8 + tw + 10 > width ? r.x - tw - 18 : r.x + 8;
  ctx.fillStyle = '#2b2850'; ctx.fillRect(lx, ly - 9, tw + 10, 18);
  ctx.strokeStyle = '#8f87e6'; ctx.lineWidth = 0.8; ctx.strokeRect(crisp(lx), crisp(ly - 9), Math.round(tw + 10), 18);
  ctx.fillStyle = '#cfcaff'; ctx.fillText(r.text, lx + 5, ly + 0.5);
}

/** A small text tag (the stats ladder), drawn by price. */
interface Note { x: number; y: number; text: string; up: boolean }

class GamePlanRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly lines: readonly Line[], private readonly runs: readonly RunBox[] = [], private readonly ahead: readonly AheadBox[] = [],
    private readonly notes: readonly Note[] = [], private readonly fades: readonly FadeBox[] = [],
    private readonly rulers: readonly Ruler[] = []) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      // Heads-up: stats stacked just ahead of price, before any of them is hit.
      for (const a of this.ahead) {
        const w = 34;
        const top = Math.min(a.yPrice, a.yFar); const h = Math.abs(a.yFar - a.yPrice);
        ctx.fillStyle = a.up ? 'rgba(47, 182, 124, 0.10)' : 'rgba(224, 87, 74, 0.10)';
        ctx.fillRect(a.x, top, w, h);
        ctx.strokeStyle = a.up ? 'rgba(47, 182, 124, 0.75)' : 'rgba(224, 87, 74, 0.75)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.strokeRect(crisp(a.x), crisp(top), w, Math.round(h));
        ctx.setLineDash([]);
        for (const y of a.ys) { ctx.beginPath(); ctx.moveTo(a.x + 4, crisp(y)); ctx.lineTo(a.x + w - 4, crisp(y)); ctx.stroke(); }
        ctx.font = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'left';
        // label right by the current price (the far end can be off screen): below it for stats above, above it for stats below
        ctx.textBaseline = 'middle';
        const tw = ctx.measureText(a.text).width;
        const lx = Math.max(4, Math.min(a.x, mediaSize.width - tw - 12));
        const ly = a.up ? a.yPrice + 12 : a.yPrice - 12;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.9)';
        ctx.fillRect(lx - 3, ly - 8, tw + 8, 16);
        ctx.fillStyle = a.up ? '#5fd3a0' : '#ff8a7a';
        ctx.fillText(a.text, lx + 1, ly + 0.5);
      }
      for (const r of this.rulers) drawRuler(ctx, r, mediaSize.width);
      // Stats ladder: "▲ next 45 pts · 3 within 50 · 17 within 150"
      for (const n of this.notes) {
        ctx.font = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        const tw = ctx.measureText(n.text).width;
        const lx = Math.max(4, Math.min(n.x, mediaSize.width - tw - 12));
        ctx.fillStyle = 'rgba(19, 23, 34, 0.92)';
        ctx.fillRect(lx - 3, n.y - 8, tw + 8, 16);
        ctx.strokeStyle = n.up ? 'rgba(47, 182, 124, 0.55)' : 'rgba(224, 87, 74, 0.55)';
        ctx.lineWidth = 1;
        ctx.strokeRect(crisp(lx - 3), crisp(n.y - 8), Math.round(tw + 8), 16);
        ctx.fillStyle = n.up ? '#5fd3a0' : '#ff8a7a';
        ctx.fillText(n.text, lx + 1, n.y + 0.5);
      }
      // Run fades: entry line, red zone to the stop, green zone to the target, result at the exit.
      for (const f of this.fades) {
        const x = Math.min(f.x0, f.x1); const w = Math.max(24, Math.abs(f.x1 - f.x0));
        const zone = (ya: number, yb: number, fill: string) => { ctx.fillStyle = fill; ctx.fillRect(x, Math.min(ya, yb), w, Math.abs(yb - ya)); };
        zone(f.yEntry, f.yStop, 'rgba(163, 45, 45, 0.30)');
        zone(f.yEntry, f.yTarget, 'rgba(59, 109, 17, 0.30)');
        ctx.strokeStyle = '#E24B4A'; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(x, crisp(f.yStop)); ctx.lineTo(x + w, crisp(f.yStop)); ctx.stroke();
        ctx.strokeStyle = '#8fd15a';
        ctx.beginPath(); ctx.moveTo(x, crisp(f.yTarget)); ctx.lineTo(x + w, crisp(f.yTarget)); ctx.stroke();
        ctx.strokeStyle = '#d8dbe2'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(x, crisp(f.yEntry)); ctx.lineTo(x + w, crisp(f.yEntry)); ctx.stroke(); ctx.setLineDash([]);
        ctx.font = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
        const top = Math.min(f.yStop, f.yTarget) - 4;
        const tw = ctx.measureText(f.text).width;
        ctx.fillStyle = 'rgba(19, 23, 34, 0.9)'; ctx.fillRect(x, top - 14, tw + 8, 15);
        ctx.fillStyle = '#e9b040'; ctx.fillText(f.text, x + 4, top);
        if (f.result) {
          const rw = ctx.measureText(f.result).width;
          ctx.fillStyle = f.win === null ? '#2a5b8f' : f.win ? '#3B6D11' : '#A32D2D';
          ctx.fillRect(x + w + 4, f.yEntry - 9, rw + 10, 18);
          ctx.fillStyle = '#fff'; ctx.textBaseline = 'middle'; ctx.fillText(f.result, x + w + 9, f.yEntry + 0.5);
        }
      }
      // Stat runs: a soft box around the checkmarks that came one after another.
      for (const r of this.runs) {
        const x = Math.min(r.x0, r.x1) - 6; const w = Math.abs(r.x1 - r.x0) + 12;
        const y = Math.min(r.y0, r.y1) - 6; const h = Math.abs(r.y1 - r.y0) + 12;
        ctx.fillStyle = r.up ? 'rgba(47, 182, 124, 0.13)' : 'rgba(224, 87, 74, 0.13)';
        ctx.strokeStyle = r.up ? 'rgba(47, 182, 124, 0.7)' : 'rgba(224, 87, 74, 0.7)';
        ctx.lineWidth = 1;
        ctx.fillRect(x, y, w, h);
        ctx.strokeRect(crisp(x), crisp(y), Math.round(w), Math.round(h));
        ctx.font = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        const tw = ctx.measureText(r.text).width;
        const ty = Math.max(16, y - 3); // label above the box, where the run started
        ctx.fillStyle = 'rgba(19, 23, 34, 0.85)';
        ctx.fillRect(x, ty - 14, tw + 8, 14);
        ctx.fillStyle = r.up ? '#5fd3a0' : '#ff8a7a';
        ctx.fillText(r.text, x + 4, ty - 1);
      }
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

class GamePlanAheadView implements IPrimitivePaneView {
  constructor(private readonly primitive: GamePlanPrimitive) {}
  zOrder(): PrimitivePaneViewZOrder { return 'top'; }
  renderer(): IPrimitivePaneRenderer | null { return this.primitive.createAheadRenderer(); }
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
  /** heads-up settings (from the Game Plan store) */
  ahead = { minCount: 4, reachES: 12, reachNQ: 50, runMin: 4, ladder: true, runs: false, fade: true, fadeMin: 8, fadeTrigger: 0.25, fadeTarget: 0.5 };
  /** the chart's candles, for the run fade */
  bars: readonly { timestamp_ms: number; high: number | string; low: number | string; close: number | string }[] = [];
  private t = 0;
  private price = 0;
  private readonly views: readonly IPrimitivePaneView[] = [new GamePlanPaneView(this), new GamePlanAheadView(this)];

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

  /** Heads-up brackets, drawn on top (Replay's curtain covers the space right of the last candle). */
  createAheadRenderer(): IPrimitivePaneRenderer | null {
    const plan = this.plan;
    const series = this.params?.series;
    if (!plan || !series) return null;
    const aheads: AheadBox[] = [];
    const nowX = this.x(this.t);
    const yNow = series.priceToCoordinate(this.price);
    if (nowX !== null && yNow !== null && this.price) {
      const family = (plan.market?.family ?? plan.symbol ?? '').toUpperCase().includes('NQ') ? 'NQ' : 'ES';
      const reach = family === 'NQ' ? this.ahead.reachNQ : this.ahead.reachES;
      const found = statsAhead(plan.levels, this.t, this.price, reach, this.ahead.minCount);
      const pts = (v: number) => (Math.round(v * 4) / 4).toString();
      for (const [st, up] of [[found.up, true], [found.down, false]] as const) {
        if (!st) continue;
        const yFar = series.priceToCoordinate(st.far);
        if (yFar === null) continue;
        const ys = st.prices.map((p) => series.priceToCoordinate(p)).filter((v): v is NonNullable<typeof v> => v !== null).map(Number);
        aheads.push({ x: nowX + 14, yPrice: Number(yNow), yFar: Number(yFar), ys, up,
          text: `${up ? '▲' : '▼'} ${st.count} stats within ${pts(Math.abs(st.far - this.price))} pts` });
      }
    }
    // Stats ladder by price, always on (unless switched off): distance to the next stats each way.
    const notes: Note[] = [];
    if (this.ahead.ladder && nowX !== null && yNow !== null && this.price) {
      const nq = (plan.market?.family ?? plan.symbol ?? '').toUpperCase().includes('NQ');
      const tiers = nq ? [100, 400] : [25, 100];
      const lad = statsLadder(plan.levels, this.t, this.price, tiers);
      const f = (v: number) => (v >= 10 ? Math.round(v).toString() : (Math.round(v * 4) / 4).toString());
      const shift = aheads.length ? 40 : 0;     // keep clear of a heads-up label
      for (const [s, up] of [[lad.up, true], [lad.down, false]] as const) {
        if (s.next === null) continue;
        notes.push({ x: nowX + 14, y: Number(yNow) + (up ? -(26 + shift) : 26 + shift), up,
          text: `${up ? '▲' : '▼'} next stat ${f(s.next)} pts · ${s.counts[0]} within ${tiers[0]} · ${s.counts[1]} within ${tiers[1]}` });
      }
    }
    // "I" from price back to where the latest run started
    const rulers: Ruler[] = [];
    const last = this.ahead.runs ? statRuns(plan.levels, this.t, this.ahead.runMin).pop() : undefined;
    if (last && nowX !== null && yNow !== null && this.price) {
      // from price to the far end of the run (its low for a run down, its high for a run up)
      const end = last.dir > 0 ? last.hi : last.lo;
      const ys = series.priceToCoordinate(end);
      if (ys !== null && Math.abs(Number(ys) - Number(yNow)) > 4)
        rulers.push({ x: nowX + 6, ya: Number(yNow), yb: Number(ys),
          text: `${fmtPts(Math.abs(this.price - end))} pts ${this.price > end ? 'above' : 'below'} the run ${last.dir > 0 ? 'high' : 'low'}` });
    }
    return aheads.length || notes.length || rulers.length ? new GamePlanRenderer([], [], aheads, notes, [], rulers) : null;
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
    const runs: RunBox[] = [];
    const boxRulers: Ruler[] = [];
    const shownRuns = this.ahead.runs ? statRuns(plan.levels, this.t, this.ahead.runMin) : [];
    for (const r of shownRuns as StatRun[]) {
      const x0 = this.x(r.from); const x1 = this.x(r.to);
      const y0 = series.priceToCoordinate(r.lo); const y1 = series.priceToCoordinate(r.hi);
      if (x0 === null || x1 === null || y0 === null || y1 === null) continue;
      runs.push({ x0, x1, y0: Number(y0), y1: Number(y1), up: r.dir > 0, text: `${r.count} stats in a row ${r.dir > 0 ? '▲' : '▼'}` });
      boxRulers.push({ x: Math.max(x0, x1) + 12, ya: Number(y0), yb: Number(y1), text: `${fmtPts(r.hi - r.lo)} pts` });
    }
    // Every checkmark inside a run, not only the latest few, so the stack reads as one.
    for (const r of shownRuns) {
      for (const l of plan.levels) {
        if (l.hitAt === null || l.hitAt < r.from || l.hitAt > r.to || l.kind !== 'target' || lines.some((x) => x.hitX !== null && x.y === series.priceToCoordinate(l.price))) continue;
        const y = series.priceToCoordinate(l.price); const hx = this.x(l.hitAt);
        if (y === null || hx === null || (r.dir > 0) !== (l.side === 'up') || l.group === 'Hour' || l.group === 'Hour zones') continue;
        lines.push({ y: Number(y), x0: Math.max(0, hx - STUB_PX), x1: hx, color: l.color, dashed: false, faded: true, hitX: hx, label: null });
      }
    }
    // Run fades (trade the give-back of a big run, like the QuickTrade box)
    const fades: FadeBox[] = [];
    if (this.ahead.fade && this.bars.length) {
      const nq = (plan.market?.family ?? plan.symbol ?? '').toUpperCase().includes('NQ');
      const found: RunFade[] = runFades(plan.levels, this.bars, this.t, plan.end, {
        minCount: this.ahead.fadeMin, trigger: this.ahead.fadeTrigger, target: this.ahead.fadeTarget,
        pad: nq ? 4 : 1, maxHoldMs: 6 * 3600_000,
      });
      const r = (v: number) => (Math.round(v * 4) / 4).toLocaleString('en-US', { maximumFractionDigits: 2 });
      for (const f of found) {
        const x0 = this.x(f.entryT); const x1 = this.x(f.exitT ?? this.t);
        const ye = series.priceToCoordinate(f.entry); const ys = series.priceToCoordinate(f.stop); const yt = series.priceToCoordinate(f.target);
        if (x0 === null || x1 === null || ye === null || ys === null || yt === null) continue;
        const live = f.how === null ? (this.price - f.entry) * f.dir : null;
        const result = f.how === null
          ? `open ${live! >= 0 ? '+' : ''}${r(live!)} pts`
          : `${f.how === 'target' ? 'target' : f.how === 'stop' ? 'stop' : 'time'} ${f.pts! >= 0 ? '+' : ''}${r(f.pts!)} pts`;
        fades.push({ x0, x1, yEntry: Number(ye), yStop: Number(ys), yTarget: Number(yt), result,
          win: f.how === null ? null : f.pts! > 0,
          text: `Run fade ${f.dir > 0 ? '▲' : '▼'} (${f.run.count}-stat run) · target ${r(f.target)} · stop ${r(f.stop)}` });
      }
    }
    return lines.length || runs.length || fades.length || boxRulers.length ? new GamePlanRenderer(lines, runs, [], [], fades, boxRulers) : null;
  }
}
