import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';

import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import type { SessionLevelSegment } from './sessionLevels';

/**
 * Fractal Manipulation Projections: at every clock hour, dashed rails at the open +/- k sigma for
 * each time slice (5 ... 30 minutes), labelled "30m +1.5σ (11:00)", and curves through the
 * equal-sigma points that fan out from the open. The open itself is a solid blue line.
 */

export interface FmpGuide {
  kind: 'fmp';
  slices: number[];
  open_color: string;
  up_color: string;
  down_color: string;
  odds: Record<string, string>;
}

export interface FmpOptions {
  sigmas: number[];
  slices: number[];
  curves: 'curved' | 'straight' | 'off';
  hoursBack: number;
  barSeconds: number;
}

export interface CurveLine {
  points: { time: number; price: number }[];
  color: string;
  width: number;
  smooth: boolean;
}

export function readFmpGuide(guide: JsonObject | undefined): FmpGuide | null {
  if (!guide || guide.kind !== 'fmp' || !Array.isArray(guide.slices)) return null;
  return guide as unknown as FmpGuide;
}

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const clock = new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'America/New_York' });

export function parseList(raw: unknown, fallback: number[]): number[] {
  const values = String(raw ?? '')
    .split(/[,\s]+/)
    .map(Number)
    .filter((v) => Number.isFinite(v) && v > 0);
  return values.length ? [...new Set(values)].sort((a, b) => a - b) : fallback;
}

const sigmaText = (k: number): string => `${k}σ`;

export function layoutFmp(
  points: readonly IndicatorDataPoint[],
  guide: FmpGuide,
  options: FmpOptions,
): { segments: SessionLevelSegment[]; curves: CurveLine[] } {
  // One row per hour: its first bar (for the start) and its last loaded bar.
  const hours = new Map<number, { first: IndicatorDataPoint; lastTime: number }>();
  for (const p of points) {
    const start = num(p, 'start');
    const t = Number(p.timestamp_ms);
    if (start === null || !Number.isFinite(t)) continue;
    const row = hours.get(start);
    if (!row) hours.set(start, { first: p, lastTime: t });
    else row.lastTime = Math.max(row.lastTime, t);
  }
  const starts = [...hours.keys()].sort((a, b) => a - b).slice(-Math.max(1, options.hoursBack));
  const slices = options.slices.filter((s) => guide.slices.includes(s));
  const segments: SessionLevelSegment[] = [];
  const curves: CurveLine[] = [];

  for (const startMs of starts) {
    const { first, lastTime } = hours.get(startMs)!;
    const open = num(first, 'open');
    if (open === null) continue;
    const start = Math.floor(startMs / 1000);
    const lastBar = Math.floor(lastTime / 1000);
    const name = clock.format(new Date(startMs));
    const base = {
      lineWidth: 1, touch: null, showPrice: false, compact: true, noAutoscale: false,
    } as const;
    segments.push({
      ...base,
      id: `fmp-open-${start}`,
      startTime: start,
      endTime: Math.min(lastBar, start + 45 * 60),
      sessionEndTime: start + 45 * 60 - options.barSeconds,
      price: open,
      label: '',
      color: guide.open_color,
      labelColor: guide.open_color,
      lineWidth: 2,
      lineStyle: 0,
      hoverLines: [`${name} hour open`, 'The rails measure from here.'],
    });
    for (const k of options.sigmas) {
      for (const dir of [1, -1] as const) {
        const color = dir > 0 ? guide.up_color : guide.down_color;
        const sign = dir > 0 ? '+' : '-';
        const curve: CurveLine = { points: [{ time: start, price: open }], color, width: 1, smooth: options.curves === 'curved' };
        for (const s of slices) {
          const sig = num(first, `sig${s}`);
          if (sig === null) continue;
          const price = open + dir * k * sig;
          // Each rail runs from the open to its own slice time, where its label sits (like the original).
          const railEnd = start + s * 60;
          segments.push({
            ...base,
            id: `fmp-${start}-${s}-${dir}-${k}`,
            startTime: start,
            endTime: Math.min(lastBar, railEnd),
            sessionEndTime: railEnd,
            price,
            label: `${s}m ${sign}${sigmaText(k)} (${name})`,
            color: 'rgba(154, 164, 178, 0.55)',
            labelColor: 'rgba(200, 206, 214, 0.75)',
            lineStyle: 2,
            hoverLines: [
              `${name} hour · ${s} min · ${sign}${sigmaText(k)}`,
              `${k} sigma ${dir > 0 ? 'above' : 'below'} the open: ${(k * sig).toFixed(2)} points after ${s} minutes.`,
              `${guide.odds[String(k)] ?? ''}${guide.odds[String(k)] ? ' (either side).' : ''}`,
            ].filter(Boolean),
          });
          curve.points.push({ time: start + s * 60, price });
        }
        if (options.curves !== 'off' && curve.points.length > 1) curves.push(curve);
      }
    }
  }
  return { segments, curves };
}

/** Pixel path through the points: straight, or Catmull-Rom as cubic Béziers. */
export function curvePath(pts: { x: number; y: number }[], smooth: boolean): { x: number; y: number; c1?: { x: number; y: number }; c2?: { x: number; y: number } }[] {
  if (!smooth || pts.length < 3) return pts.map((p) => ({ ...p }));
  const out: { x: number; y: number; c1?: { x: number; y: number }; c2?: { x: number; y: number } }[] = [{ ...pts[0] }];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    out.push({
      x: p2.x,
      y: p2.y,
      c1: { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 },
      c2: { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 },
    });
  }
  return out;
}

export class CurveRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly curves: { pts: { x: number; y: number }[]; color: string; width: number; smooth: boolean }[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.save();
      for (const c of this.curves) {
        const path = curvePath(c.pts, c.smooth);
        if (path.length < 2) continue;
        ctx.strokeStyle = c.color;
        ctx.lineWidth = c.width;
        ctx.beginPath();
        ctx.moveTo(path[0].x, path[0].y);
        for (const p of path.slice(1)) {
          if (p.c1 && p.c2) ctx.bezierCurveTo(p.c1.x, p.c1.y, p.c2.x, p.c2.y, p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }
      ctx.restore();
    });
  }
}
