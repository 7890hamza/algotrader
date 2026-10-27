import type { IndicatorDataPoint, IndicatorOutputMetadata, JsonObject } from '@/types/contracts';

/** Output type for indicators drawn as labeled horizontal session levels. */
export const LEVEL_OUTPUT_TYPE = 'level';

export type LevelTouch = 'high' | 'low';

export interface SessionLevelSegment {
  id: string;
  /** Epoch seconds of the first and last bar of the segment. */
  startTime: number;
  endTime: number;
  price: number;
  label: string;
  color: string;
  lineWidth: number;
  /** 0 solid, 1 dotted, 2 dashed (lightweight-charts LineStyle values). */
  lineStyle: number;
  touch: LevelTouch | null;
  labelColor: string;
  /** Draw the price after the label, e.g. "+1 7,801.31". */
  showPrice: boolean;
  /**
   * Start of the session's last bar (epoch seconds). The line runs to here even
   * while the session is still live, so its full window is visible.
   */
  sessionEndTime: number | null;
  /** Epoch seconds of a diamond drawn on the line (e.g. price came back to it), or null. */
  markerTime?: number | null;
  markerColor?: string;
  /** Draw the first touch as an arrow (in touchColor) instead of a circle. */
  touchShape?: 'circle' | 'arrow';
  touchColor?: string;
}

export interface SessionLevelOptions {
  /** Length of the session window; enables drawing to the end of the window. */
  sessionSeconds?: number | null;
}

const DEFAULT_COLOR = '#9aa4b2';
const DEFAULT_LABEL_COLOR = '#e6e6e6';
const PRICE_EPSILON = 1e-9;
/** A gap longer than this many bars ends a segment (session over). */
const MAX_GAP_BARS = 5;

export function isLevelOutput(output: IndicatorOutputMetadata | undefined): boolean {
  return output?.type === LEVEL_OUTPUT_TYPE;
}

export function hasLevelOutputs(outputs: Record<string, IndicatorOutputMetadata>): boolean {
  return Object.values(outputs).some(isLevelOutput);
}

function numberOption(options: JsonObject | undefined, key: string, fallback: number): number {
  const value = options?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function stringOption(options: JsonObject | undefined, key: string, fallback: string): string {
  const value = options?.[key];
  return typeof value === 'string' && value !== '' ? value : fallback;
}

function toSeconds(point: IndicatorDataPoint): number {
  return Math.floor(Number(point.timestamp_ms) / 1000);
}

function barSeconds(times: readonly number[]): number {
  let smallest = Number.POSITIVE_INFINITY;
  for (let i = 1; i < times.length; i += 1) {
    const diff = times[i] - times[i - 1];
    if (diff > 0 && diff < smallest) smallest = diff;
  }
  return Number.isFinite(smallest) ? smallest : 60;
}

/**
 * Turns per-bar level values into one horizontal segment per session and level.
 * A segment ends where the value changes, disappears, or bars stop for longer
 * than a few bar lengths.
 */
export function buildSessionLevelSegments(
  points: readonly IndicatorDataPoint[],
  outputs: Record<string, IndicatorOutputMetadata>,
  styleOverrides: Record<string, JsonObject> = {},
  levelOptions: SessionLevelOptions = {},
): SessionLevelSegment[] {
  const sorted = [...points]
    .filter((point) => Number.isFinite(toSeconds(point)))
    .sort((a, b) => toSeconds(a) - toSeconds(b));
  const times = sorted.map(toSeconds);
  const bar = barSeconds(times);
  const maxGap = bar * MAX_GAP_BARS;
  const sessionSeconds = levelOptions.sessionSeconds ?? null;
  const segments: SessionLevelSegment[] = [];

  for (const [outputKey, output] of Object.entries(outputs)) {
    if (!isLevelOutput(output)) continue;

    const options: JsonObject = { ...(output.plotOptions ?? {}), ...(styleOverrides[outputKey] ?? {}) };
    const label = typeof output.label === 'string' ? output.label : outputKey;
    const touch = output.touch === 'high' || output.touch === 'low' ? output.touch : null;
    const labelColor = typeof output.labelColor === 'string' ? output.labelColor : DEFAULT_LABEL_COLOR;
    const showPrice = output.showPrice === true;
    // extend: false keeps the line to its own bars (it doesn't start at the session open).
    const toSessionEnd = output.extend !== false;
    // markerFrom names an output holding epoch ms; a diamond goes on the line at that time.
    const markerKey = typeof output.markerFrom === 'string' ? output.markerFrom : null;
    const markerColor = typeof output.markerColor === 'string' ? output.markerColor : undefined;
    // touchWhen {key, equals}: mark the touch only on sessions where that output has that value
    // (e.g. only the line that was touched first).
    const when = output.touchWhen as { key?: unknown; equals?: unknown } | undefined;
    const whenKey = when && typeof when.key === 'string' ? when.key : null;
    const touchShape = output.touchShape === 'arrow' ? 'arrow' : undefined;
    const touchColor = typeof output.touchColor === 'string' ? output.touchColor : undefined;
    let current: SessionLevelSegment | null = null;

    const close = (): void => {
      if (current) segments.push(current);
      current = null;
    };

    for (let i = 0; i < sorted.length; i += 1) {
      const value = sorted[i][outputKey];
      const time = times[i];
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        close();
        continue;
      }

      const markerMs = markerKey ? sorted[i][markerKey] : null;
      const markerTime = typeof markerMs === 'number' && Number.isFinite(markerMs) ? Math.floor(markerMs / 1000) : null;
      const whenMet = whenKey !== null && sorted[i][whenKey] === when?.equals;
      const seg = current as SessionLevelSegment | null;
      if (seg && Math.abs(seg.price - value) <= PRICE_EPSILON && time - seg.endTime <= maxGap) {
        seg.endTime = time;
        if (markerTime !== null) seg.markerTime = markerTime;
        if (whenMet) seg.touch = touch;
        continue;
      }

      close();
      current = {
        id: `${outputKey}@${time}`,
        startTime: time,
        endTime: time,
        price: value,
        label,
        color: stringOption(options, 'color', DEFAULT_COLOR),
        lineWidth: numberOption(options, 'lineWidth', 1),
        lineStyle: numberOption(options, 'lineStyle', 0),
        touch: whenKey === null || whenMet ? touch : null,
        touchShape,
        touchColor,
        labelColor,
        showPrice,
        markerTime,
        markerColor,
        sessionEndTime: toSessionEnd && sessionSeconds && sessionSeconds > bar ? time + sessionSeconds - bar : null,
      };
    }
    close();
  }

  return segments;
}

/** Minutes after midnight for "HH:MM", or null. */
export function clockMinutes(value: unknown): number | null {
  if (typeof value !== 'string') return null;
  const match = /^\s*(\d{1,2}):(\d{2})\s*$/.exec(value);
  if (!match) return null;
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return minutes < 1440 ? minutes : null;
}

/** "7801.3125" -> "7,801.31" */
export function formatLevelPrice(price: number, precision = 2): string {
  return price.toLocaleString('en-US', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  });
}

export interface LevelCandle {
  time: number;
  high: number;
  low: number;
}

/**
 * Time of the first candle inside the segment that reached its price, or null.
 * `candles` must be sorted by time.
 */
export function firstTouchTime(
  segment: SessionLevelSegment,
  candles: readonly LevelCandle[],
): number | null {
  if (!segment.touch) return null;
  let lo = 0;
  let hi = candles.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (candles[mid].time < segment.startTime) lo = mid + 1;
    else hi = mid;
  }
  for (let i = lo; i < candles.length && candles[i].time <= segment.endTime; i += 1) {
    const candle = candles[i];
    if (segment.touch === 'high' ? candle.high >= segment.price : candle.low <= segment.price) {
      return candle.time;
    }
  }
  return null;
}

/** Inserts or replaces a point by timestamp, keeping the array sorted. */
export function upsertIndicatorPoint(
  points: IndicatorDataPoint[],
  point: IndicatorDataPoint,
): IndicatorDataPoint[] {
  const ts = Number(point.timestamp_ms);
  const last = points[points.length - 1];
  if (!last || Number(last.timestamp_ms) < ts) {
    points.push(point);
    return points;
  }
  const index = points.findIndex((item) => Number(item.timestamp_ms) >= ts);
  if (index >= 0 && Number(points[index].timestamp_ms) === ts) {
    points[index] = point;
  } else if (index >= 0) {
    points.splice(index, 0, point);
  }
  return points;
}
