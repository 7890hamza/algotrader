import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import type { SessionLevelSegment } from './sessionLevels';

/** One engulfing candle as drawn on the chart. */
export interface CandleMark {
  /** Epoch seconds of the engulfing candle. */
  time: number;
  side: 1 | -1;
  /** The engulfing body. */
  top: number;
  bottom: number;
  /** Name of the level the candle formed at ("London H"), or null. */
  atLevel: string | null;
  /** +1 ran one body in its favour, -1 invalidated first, 0 still open, null unknown. */
  outcome: number | null;
  mae: number | null;
  mfe: number | null;
  /** Epoch seconds of the close that invalidated it, or null. */
  invalAt: number | null;
  invalPrice: number;
  /** Lines for the hover card. */
  lines: string[];
}

/** A level drawn by another indicator, used to spot engulfings that form at it. */
export interface NearbyLevel {
  price: number;
  label: string;
  startTime: number;
  endTime: number;
}

export const BULL_COLOR = '#3FB950';
export const BEAR_COLOR = '#E0574A';
const BROKEN_COLOR = '#6E7681';
/** A level within this many points of the engulfing body counts as "at the level". */
export const DEFAULT_NEAR_POINTS = 2;

export function isEngulfingGuide(guide: JsonObject | undefined): boolean {
  return guide?.kind === 'engulfing';
}

const num = (point: IndicatorDataPoint, key: string): number | null => {
  const value = point[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const pts = (value: number): string => value.toFixed(2).replace(/\.?0+$/, '');

const clockFormats = new Map<string, Intl.DateTimeFormat>();
function clock(epochSeconds: number, timeZone: string): string {
  let format = clockFormats.get(timeZone);
  if (!format) {
    format = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone });
    clockFormats.set(timeZone, format);
  }
  return format.format(new Date(epochSeconds * 1000));
}

function sorted(points: readonly IndicatorDataPoint[]): IndicatorDataPoint[] {
  return [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)))
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
}

/** The level (if any) whose price sits within `near` points of the body at `time`. */
function levelAt(time: number, top: number, bottom: number, levels: readonly NearbyLevel[], near: number): NearbyLevel | null {
  let best: NearbyLevel | null = null;
  let bestDistance = Infinity;
  for (const level of levels) {
    if (time < level.startTime || time > level.endTime) continue;
    const distance = level.price > top ? level.price - top : level.price < bottom ? bottom - level.price : 0;
    if (distance <= near && distance < bestDistance) {
      best = level;
      bestDistance = distance;
    }
  }
  return best;
}

/** Every engulfing candle in the points, with its result and the level it formed at. */
export function buildEngulfingMarks(
  points: readonly IndicatorDataPoint[],
  levels: readonly NearbyLevel[] = [],
  timeZone = 'America/Los_Angeles',
  near = DEFAULT_NEAR_POINTS,
): CandleMark[] {
  const marks: CandleMark[] = [];
  for (const point of sorted(points)) {
    const signal = num(point, 'signal');
    const top = num(point, 'body_top');
    const bottom = num(point, 'body_bot');
    if ((signal !== 1 && signal !== -1) || top === null || bottom === null) continue;
    const time = Math.floor(Number(point.timestamp_ms) / 1000);
    const side = signal as 1 | -1;
    const invalPrice = side === 1 ? bottom : top;
    const invalMs = num(point, 'inval_at');
    const invalAt = invalMs === null ? null : Math.floor(invalMs / 1000);
    const outcome = num(point, 'outcome');
    const mae = num(point, 'mae');
    const mfe = num(point, 'mfe');
    const level = levelAt(time, top, bottom, levels, near);
    const name = side === 1 ? 'Bullish engulfing' : 'Bearish engulfing';
    const lines = [
      `${name} · ${clock(time, timeZone)}${level ? ` · at ${level.label}` : ''}`,
      `Body ${pts(top - bottom)} pts. Invalidated by a close ${side === 1 ? 'below' : 'above'} ${pts(invalPrice)}.`,
    ];
    if (mfe !== null && mae !== null) lines.push(`Went with it ${pts(mfe)} pts (MFE) · against it ${pts(mae)} pts (MAE)`);
    if (outcome === 1) lines.push('✓ Ran one body before it was invalidated');
    else if (outcome === -1 && invalAt !== null) lines.push(`✕ Invalidated at ${clock(invalAt, timeZone)}`);
    else lines.push('Still open: not invalidated yet');
    marks.push({ time, side, top, bottom, atLevel: level?.label ?? null, outcome, mae, mfe, invalAt, invalPrice, lines });
  }
  return marks;
}

/**
 * Invalidation lines: from the engulfing candle to the close that broke it, or to the
 * last bar while it still holds. Lines still holding are always drawn (with a label);
 * finished ones only for candles that formed at a level, to keep the chart clean.
 */
export function buildEngulfingLines(points: readonly IndicatorDataPoint[], marks: readonly CandleMark[]): SessionLevelSegment[] {
  const rows = sorted(points);
  const times = rows.map((p) => Math.floor(Number(p.timestamp_ms) / 1000));
  const lastTime = times.length ? times[times.length - 1] : 0;
  const lines: SessionLevelSegment[] = [];
  marks.forEach((mark, i) => {
    let endTime = mark.invalAt;
    if (endTime === null) {
      // Still holding, or past the measuring window: follow the line while it is drawn.
      const key = mark.side === 1 ? 'inval_bull' : 'inval_bear';
      let k = times.indexOf(mark.time);
      while (k + 1 < rows.length && num(rows[k + 1], key) === mark.invalPrice) k += 1;
      endTime = k >= 0 ? times[k] : mark.time;
    }
    const live = mark.invalAt === null && endTime === lastTime;
    if (!live && mark.atLevel === null) return;
    const color = mark.invalAt !== null ? BROKEN_COLOR : mark.side === 1 ? BULL_COLOR : BEAR_COLOR;
    lines.push({
      id: `engulfing-${i}`,
      startTime: mark.time,
      endTime,
      price: mark.invalPrice,
      label: live ? `${mark.side === 1 ? 'Bull' : 'Bear'} invalidation` : '',
      color,
      lineWidth: 1,
      lineStyle: 2,
      touch: null,
      labelColor: color,
      showPrice: live,
      sessionEndTime: null,
    });
  });
  return lines;
}

/** "Follow-through (MFE) · P75" -> "Follow-through P75": short enough to sit under a candle. */
export function shortLevelName(label: string): string {
  return label.replace(/\([^)]*\)/g, '').replace(/[·]/g, ' ').replace(/\s+/g, ' ').trim();
}
