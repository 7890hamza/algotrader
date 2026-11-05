import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';

import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import { formatClock, formatPrice, type SessionBox } from './alnGuide';
import type { SessionLevelSegment } from './sessionLevels';

/** Breaks' retracement layer: legs (zigzag), 40-60% zones, "Out" marks and trend changes. */
export interface RetraceMark {
  time: number;
  price: number;
  text: string;
  color: string;
  /** Circle around the point ("Out") or a plain label ("Trend change"). */
  circle: boolean;
  /** Text below (true) or above the point. */
  below: boolean;
}

export interface RetraceLayer {
  legs: { time: number; price: number }[];
  marks: RetraceMark[];
  color: string;
}

export interface RetraceBuild {
  layer: RetraceLayer | null;
  boxes: SessionBox[];
  segments: SessionLevelSegment[];
}

interface RetraceColors {
  zone: [number, number];
  up: string;
  down: string;
  leg: string;
}

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

function readColors(guide: JsonObject | undefined): RetraceColors | null {
  const r = guide?.retrace as JsonObject | undefined;
  if (!r) return null;
  const zone = Array.isArray(r.zone) && r.zone.length === 2 ? (r.zone as [number, number]) : [0.4, 0.6];
  return {
    zone: zone as [number, number],
    up: typeof r.up === 'string' ? r.up : '#3FB950',
    down: typeof r.down === 'string' ? r.down : '#E0574A',
    leg: typeof r.leg === 'string' ? r.leg : '#E9C46A',
  };
}

function level(id: string, start: number, end: number, price: number, label: string, color: string, style: number): SessionLevelSegment {
  return {
    id, startTime: start, endTime: end, price, label, color, lineWidth: 1, lineStyle: style, touch: null,
    labelColor: '#9aa4b2', showPrice: false, sessionEndTime: null, compact: true, noAutoscale: true,
  };
}

/** Turns Breaks' rt_* outputs into zones, the zone's 40 / 60 / 100% lines, legs and marks. */
export function buildRetrace(points: readonly IndicatorDataPoint[], guide: JsonObject | undefined, timeZone: string): RetraceBuild {
  const colors = readColors(guide);
  const empty: RetraceBuild = { layer: null, boxes: [], segments: [] };
  if (!colors) return empty;
  const sorted = [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)))
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  const groups: IndicatorDataPoint[][] = [];
  for (const p of sorted) {
    const zone = num(p, 'rt_zone');
    if (zone === null) continue;
    const g = groups[groups.length - 1];
    const prev = g?.[g.length - 1];
    if (g && prev && num(prev, 'rt_zone') === zone && Number(p.timestamp_ms) - Number(prev.timestamp_ms) < 3 * 3_600_000) g.push(p);
    else groups.push([p]);
  }
  if (!groups.length) return empty;
  // Only the latest session's staircase: earlier days would clutter the chart.
  let first = groups.length - 1;
  while (first > 0) {
    const gap = Number(groups[first][0].timestamp_ms) - Number(groups[first - 1][groups[first - 1].length - 1].timestamp_ms);
    if (gap > 3 * 3_600_000) break;
    first -= 1;
  }
  groups.splice(0, first);
  const lastPoint = sorted[sorted.length - 1];
  const lastTime = Math.floor(Number(lastPoint.timestamp_ms) / 1000);
  const clock = (ms: number): string => formatClock(ms, timeZone);
  const out: RetraceBuild = { layer: { legs: [], marks: [], color: colors.leg }, boxes: [], segments: [] };
  const [z40, z60] = colors.zone;
  let prevFlip: number | null = null;
  groups.forEach((g, k) => {
    const first = g[0];
    const last = g[g.length - 1];
    const dir = num(last, 'rt_dir') ?? 1;
    const start = num(last, 'rt_start')!;
    const end = num(last, 'rt_end')!;
    const startAt = Math.floor(num(last, 'rt_start_at')! / 1000);
    const endAt = Math.floor(num(last, 'rt_end_at')! / 1000);
    const p40 = end - z40 * (end - start);
    const p60 = end - z60 * (end - start);
    const live = last === lastPoint;
    const color = dir > 0 ? colors.up : colors.down;
    const t1 = Math.floor(Number(last.timestamp_ms) / 1000);
    const outAt = num(last, 'rt_out_at');
    const outPx = num(last, 'rt_out_px');
    const res = num(last, 'rt_res');
    const word = dir > 0 ? 'high' : 'low';
    const hover = [
      `40–60% retracement zone (${dir > 0 ? 'uptrend' : 'downtrend'})`,
      `Leg ${formatPrice(start)} → ${formatPrice(end)} (${formatPrice(Math.abs(end - start))} pts): price usually rests ${formatPrice(Math.min(p40, p60))}–${formatPrice(Math.max(p40, p60))} before the next step.`,
      outAt !== null && outPx !== null
        ? `Came back out at ${clock(outAt)} (${formatPrice(outPx)})${res === 1 ? ` and made a new ${word} ✓` : res === -1 ? ` but broke ${formatPrice(start)} first ✗` : ''}.`
        : 'Waiting for price to dip into the zone and come back out.',
      `Past ${formatPrice(start)} (100%) the trend changes.`,
      'The zone shows where to look. The entry is when price turns back out of it.',
    ];
    if (endAt <= t1) {
      out.boxes.push({
        id: `rt_zone@${endAt}`, startTime: endAt, endTime: t1, high: Math.max(p40, p60), low: Math.min(p40, p60),
        color, label: '', noLabels: true, fillOpacity: live ? 0.22 : 0.1, hoverLines: hover,
      });
      out.segments.push(level(`rt_mid@${endAt}`, endAt, t1, (p40 + p60) / 2, '', color, 1));
    }
    if (live) {
      out.segments.push(
        level(`rt_40@${endAt}`, endAt, lastTime, p40, '40%', color, 1),
        level(`rt_60@${endAt}`, endAt, lastTime, p60, '60%', color, 1),
        level(`rt_100@${endAt}`, endAt, lastTime, start, '100%', '#8a919c', 1),
      );
    }
    if (k === 0 || out.layer!.legs.length === 0) out.layer!.legs.push({ time: startAt, price: start });
    else if (out.layer!.legs[out.layer!.legs.length - 1].time !== startAt) out.layer!.legs.push({ time: startAt, price: start });
    out.layer!.legs.push({ time: endAt, price: end });
    if (outAt !== null && outPx !== null) {
      out.layer!.marks.push({
        time: Math.floor(outAt / 1000), price: outPx, circle: true, below: dir > 0,
        text: `Out${res === 1 ? ' ✓' : res === -1 ? ' ✗' : ''}`,
        color: res === 1 ? colors.up : res === -1 ? colors.down : '#d9dfe6',
      });
    }
    const flip = num(first, 'rt_flip_at');
    if (flip !== null && flip !== prevFlip) {
      out.layer!.marks.push({ time: Math.floor(flip / 1000), price: num(first, 'rt_end') ?? end, circle: false, below: dir < 0, text: 'Trend change', color });
    }
    prevFlip = flip;
  });
  return out;
}

export interface DrawnRetrace {
  legs: { x: number; y: number }[];
  marks: { mark: RetraceMark; x: number; y: number }[];
  color: string;
}

const MARK_FONT = '500 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export class RetraceRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly d: DrawnRetrace) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.save();
      if (this.d.legs.length > 1) {
        ctx.strokeStyle = this.d.color;
        ctx.lineWidth = 1.3;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        this.d.legs.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.font = MARK_FONT;
      ctx.textAlign = 'center';
      for (const { mark, x, y } of this.d.marks) {
        if (mark.circle) {
          ctx.strokeStyle = this.d.color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(x, y, 6, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.fillStyle = mark.color;
        ctx.textBaseline = mark.below ? 'top' : 'bottom';
        ctx.fillText(mark.text, x, mark.below ? y + 9 : y - 9);
      }
      ctx.restore();
    });
  }
}
