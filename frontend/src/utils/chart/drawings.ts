/**
 * Chart drawings (TradingView-style): trend line, ray, horizontal line / ray, vertical line,
 * rectangle and text. Anchored by time (ms) and price, so they stay put across timeframes, and
 * kept per symbol.
 */

export type DrawKind = 'trend' | 'ray' | 'hline' | 'hray' | 'vline' | 'rect' | 'text' | 'bookmark';
export interface DPoint { t: number; p: number }
export interface Drawing {
  id: string;
  kind: DrawKind;
  a: DPoint;
  b?: DPoint; // two-point kinds only
  color: string;
  dashed?: boolean;
  text?: string;
}

export const TWO_POINT: readonly DrawKind[] = ['trend', 'ray', 'rect'];
export const COLORS = ['#4c9ffe', '#f0b429', '#2fb67c', '#e5534b', '#b07cff', '#e6e9ef'] as const;

export const TOOLS: readonly { kind: DrawKind; label: string; key: string }[] = [
  { kind: 'trend', label: 'Trend line', key: 'Alt+T' },
  { kind: 'ray', label: 'Ray (keeps going right)', key: '' },
  { kind: 'hline', label: 'Horizontal line', key: 'Alt+H' },
  { kind: 'hray', label: 'Horizontal ray (from a point to the right)', key: 'Alt+J' },
  { kind: 'vline', label: 'Vertical line', key: 'Alt+V' },
  { kind: 'rect', label: 'Rectangle', key: 'Alt+R' },
  { kind: 'text', label: 'Text note', key: '' },
  { kind: 'bookmark', label: 'Price bookmark: drag the magnifier up / down to look at a price (Alt+B)', key: 'Alt+B' },
];

export const newId = (): string => Math.random().toString(36).slice(2, 10);
export const BOOKMARK_COLOR = '#ffcc4d';

/** Dollars per point for the symbols we trade (null = unknown). */
export function pointValue(symbol: string | null): { label: string; usd: number }[] {
  const s = (symbol ?? '').toUpperCase();
  if (s.startsWith('MES')) return [{ label: 'MES', usd: 5 }];
  if (s.startsWith('MNQ')) return [{ label: 'MNQ', usd: 2 }];
  if (s.startsWith('ES')) return [{ label: 'ES', usd: 50 }, { label: 'MES', usd: 5 }];
  if (s.startsWith('NQ')) return [{ label: 'NQ', usd: 20 }, { label: 'MNQ', usd: 2 }];
  return [];
}

/** Touches of a level since `fromT` (one per visit), the last one, and how far price has moved away since. */
export function touchInfo(bars: readonly { t: number; h: number; l: number }[], price: number, fromT: number):
  { count: number; lastT: number | null; awayPts: number | null } {
  let count = 0; let inside = false; let lastT: number | null = null; let lastIdx = -1;
  bars.forEach((b, i) => {
    if (b.t < fromT) return;
    const hit = b.l <= price && b.h >= price;
    if (hit && !inside) count += 1;
    if (hit) { lastT = b.t; lastIdx = i; }
    inside = hit;
  });
  if (lastIdx < 0 || lastIdx >= bars.length - 1) return { count, lastT, awayPts: lastIdx < 0 ? null : 0 };
  const after = bars.slice(lastIdx + 1);
  const above = bars[bars.length - 1].l > price;
  const away = above ? Math.max(...after.map((b) => b.h)) - price : price - Math.min(...after.map((b) => b.l));
  return { count, lastT, awayPts: Math.max(0, away) };
}

/** Fractional bar position of a time: between loaded bars by position, outside them by bar width. */
export function timeToLogical(times: readonly number[], barMs: number, t: number): number {
  const n = times.length;
  if (!n) return 0;
  if (t <= times[0]) return (t - times[0]) / barMs;
  if (t >= times[n - 1]) return n - 1 + (t - times[n - 1]) / barMs;
  let lo = 0; let hi = n - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (times[m] <= t) lo = m; else hi = m; }
  return lo + Math.min(1, (t - times[lo]) / Math.min(barMs, times[hi] - times[lo]));
}

/** The time at a fractional bar position (the inverse of timeToLogical). */
export function logicalToTime(times: readonly number[], barMs: number, l: number): number {
  const n = times.length;
  if (!n) return 0;
  if (l <= 0) return times[0] + l * barMs;
  if (l >= n - 1) return times[n - 1] + (l - (n - 1)) * barMs;
  const i = Math.floor(l);
  return times[i] + (l - i) * Math.min(barMs, times[i + 1] - times[i]);
}

/** How many times price came back to a level after `fromT` (back-to-back bars count once). */
export function touches(bars: readonly { t: number; h: number; l: number }[], price: number, fromT: number): number {
  let n = 0; let inside = false;
  for (const b of bars) {
    if (b.t <= fromT) continue;
    const hit = b.l <= price && b.h >= price;
    if (hit && !inside) n += 1;
    inside = hit;
  }
  return n;
}

export function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax; const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const k = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - (ax + k * dx), py - (ay + k * dy));
}

/** A ray from a through b, cut at the chart's right edge (or left edge if it points left). */
export function rayEnd(ax: number, ay: number, bx: number, by: number, width: number): [number, number] {
  if (bx === ax) return [bx, by];
  const edge = bx > ax ? width : 0;
  return [edge, ay + ((by - ay) * (edge - ax)) / (bx - ax)];
}

/** Snap a price to the nearest open / high / low / close of a bar if it's within `maxDist`. */
export function magnet(price: number, bar: { o: number; h: number; l: number; c: number } | null, maxDist: number): number {
  if (!bar) return price;
  let best = price; let bd = maxDist;
  for (const v of [bar.o, bar.h, bar.l, bar.c]) { const d = Math.abs(v - price); if (d <= bd) { bd = d; best = v; } }
  return best;
}
