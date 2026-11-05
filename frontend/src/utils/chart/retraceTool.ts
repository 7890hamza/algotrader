/**
 * Retrace tool: two anchors (the leg's start and end) and a shaded zone between any two
 * retracement percentages (40-60% by default), measured back from the second anchor toward the
 * first. Extra lines can be added at any other percentage (e.g. 50, 100, or -27 / 127 for moves
 * past the anchors).
 */
export interface RetraceAnchor {
  /** Epoch seconds of the anchor's candle. */
  time: number;
  price: number;
}

export interface RetraceDrawing {
  id: string;
  a: RetraceAnchor;
  b: RetraceAnchor;
  /** Zone edges in percent of the leg, measured back from b toward a. */
  from: number;
  to: number;
  /** Extra lines in percent. */
  lines: number[];
}

export interface RetraceLevel {
  pct: number;
  price: number;
  /** Zone edge (true) or an extra line. */
  edge: boolean;
}

export interface RetraceModel {
  /** b above a: an up leg, so retracements are below b. */
  up: boolean;
  range: number;
  zoneHigh: number;
  zoneLow: number;
  levels: RetraceLevel[];
}

export const DEFAULT_ZONE: [number, number] = [40, 60];
export const DEFAULT_LINES: number[] = [50];
const MIN_PCT = -300;
const MAX_PCT = 400;

/** The price `pct` percent of the way back from b toward a. */
export function retracePrice(d: Pick<RetraceDrawing, 'a' | 'b'>, pct: number): number {
  return d.b.price - (d.b.price - d.a.price) * (pct / 100);
}

export function buildRetraceModel(d: RetraceDrawing): RetraceModel {
  const p1 = retracePrice(d, d.from);
  const p2 = retracePrice(d, d.to);
  const pcts = new Set<number>([0, 100, d.from, d.to, ...d.lines]);
  const levels = [...pcts]
    .sort((x, y) => x - y)
    .map((pct) => ({ pct, price: retracePrice(d, pct), edge: pct === d.from || pct === d.to }));
  return {
    up: d.b.price >= d.a.price,
    range: Math.abs(d.b.price - d.a.price),
    zoneHigh: Math.max(p1, p2),
    zoneLow: Math.min(p1, p2),
    levels,
  };
}

/** "50, 100, -27" -> [50, 100, -27]; ignores anything that isn't a number in range. */
export function parseLevels(text: string): number[] {
  const out: number[] = [];
  for (const part of text.split(/[,\s;]+/)) {
    if (!part) continue;
    const v = Number(part.replace('%', ''));
    if (Number.isFinite(v) && v >= MIN_PCT && v <= MAX_PCT && !out.includes(v)) out.push(v);
  }
  return out;
}

export function clampPct(v: number): number {
  return Math.max(MIN_PCT, Math.min(MAX_PCT, Math.round(v * 10) / 10));
}

/** Snap a click to the candle's high or low, whichever is closer to where you clicked. */
export function snapToCandle(price: number, bar: { high: number; low: number } | null): number {
  if (!bar) return price;
  return Math.abs(price - bar.high) <= Math.abs(price - bar.low) ? bar.high : bar.low;
}

export function newRetrace(a: RetraceAnchor, b: RetraceAnchor, zone: [number, number] = DEFAULT_ZONE, lines: number[] = DEFAULT_LINES): RetraceDrawing {
  return { id: `rt-${a.time}-${b.time}-${Math.round(Math.random() * 1e6)}`, a, b, from: zone[0], to: zone[1], lines: [...lines] };
}

export function formatPct(p: number): string {
  return `${Number.isInteger(p) ? p : p.toFixed(1)}%`;
}
