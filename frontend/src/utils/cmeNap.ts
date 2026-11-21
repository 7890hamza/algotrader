/**
 * "CME closed" overlay: while CME is shut (2-3 PM Pacific every day, and the weekend) Hyperliquid
 * keeps trading its twins (SP500 for ES / MES, XYZ100 for NQ / MNQ). This finds those closed
 * stretches in the chart's own candles and lines Hyperliquid's price up to where CME closed, so
 * the chart shows how far it moved while CME slept and where CME reopened.
 *
 * Where Hyperliquid's price comes from (sharpest first): the app's own 1-minute recording, then
 * Hyperliquid's public API, which only keeps its newest 5,000 bars per size (1m ~3.5 days,
 * 5m ~17 days, 15m ~52 days, 1h ~7 months, 4h back to listing).
 */

export const NAP_TWIN: Record<string, string> = { ES: 'SP500', MES: 'SP500', NQ: 'XYZ100', MNQ: 'XYZ100' };

export interface Bar { t: number; c: number }

export interface Nap {
  /** last CME bar before the closure, and first after it (bar start, ms) */
  closeT: number;
  openT: number;
  closePx: number;
  openPx: number;
  weekend: boolean;
}

export interface NapResult extends Nap {
  /** Hyperliquid's price moved onto CME's scale: [ms, price], from the close to the reopen */
  line: [number, number][];
  /** where Hyperliquid was when CME reopened, on CME's scale */
  hlAtOpen: number | null;
  /** bar size the Hyperliquid price came in, in minutes (1 sharp ... 240 rough) */
  barMinutes: number;
}

/** Stretches with no CME candles longer than 45 minutes (and longer than 3 chart bars). */
export function findNaps(candles: readonly { timestamp_ms: number; open: number; close: number }[], barMs: number): Nap[] {
  const out: Nap[] = [];
  const minGap = Math.max(45 * 60_000, 3 * barMs);
  for (let i = 1; i < candles.length; i++) {
    const a = candles[i - 1];
    const b = candles[i];
    if (b.timestamp_ms - a.timestamp_ms <= minGap) continue;
    out.push({ closeT: a.timestamp_ms, openT: b.timestamp_ms, closePx: Number(a.close), openPx: Number(b.open),
      weekend: b.timestamp_ms - a.timestamp_ms > 12 * 3_600_000 });
  }
  return out;
}

/** Closing price at or before `t` (bars sorted by time). */
export function closeAt(bars: readonly Bar[], t: number): number | null {
  let lo = 0;
  let hi = bars.length - 1;
  let found: number | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].t <= t) { found = bars[mid].c; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}

/**
 * Hyperliquid bars across one closure, shifted so they start at CME's last close. `hl` holds bars
 * by their start time; a bar's close is the price at its end, so a bar counts at t + its length.
 */
export function lineUp(nap: Nap, hl: readonly Bar[], barMinutes: number, chartBarMs: number): NapResult {
  const len = barMinutes * 60_000;
  const ends = hl.map((b) => ({ t: b.t + len - chartBarMs, c: b.c })); // stamp each close where a chart bar would
  const base = closeAt(ends, nap.closeT);
  if (base === null) return { ...nap, line: [], hlAtOpen: null, barMinutes };
  const shift = nap.closePx - base;
  const line: [number, number][] = [[nap.closeT, nap.closePx]];
  for (const b of ends) if (b.t > nap.closeT && b.t < nap.openT) line.push([b.t, b.c + shift]);
  const atOpen = closeAt(ends, nap.openT - chartBarMs);
  const hlAtOpen = atOpen === null ? null : atOpen + shift;
  if (hlAtOpen !== null) line.push([nap.openT, hlAtOpen]);
  return { ...nap, line, hlAtOpen, barMinutes };
}

/** Bar sizes Hyperliquid's API still has for a closure that ended `ageMs` ago, sharpest first. */
export function apiSizes(ageMs: number): { interval: string; minutes: number }[] {
  const all = [
    { interval: '1m', minutes: 1, keepsMs: 3.3 * 86_400_000 },
    { interval: '5m', minutes: 5, keepsMs: 16.5 * 86_400_000 },
    { interval: '15m', minutes: 15, keepsMs: 51 * 86_400_000 },
    { interval: '1h', minutes: 60, keepsMs: 205 * 86_400_000 },
    { interval: '4h', minutes: 240, keepsMs: Number.POSITIVE_INFINITY },
  ];
  return all.filter((s) => s.keepsMs > ageMs).map(({ interval, minutes }) => ({ interval, minutes }));
}

/** Hyperliquid's public API: bars for one market of the trade[XYZ] venue. */
export async function fetchHyperliquidBars(twin: string, interval: string, startMs: number, endMs: number): Promise<Bar[]> {
  const res = await fetch('https://api.hyperliquid.xyz/info', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'candleSnapshot', req: { coin: `xyz:${twin}`, interval, startTime: startMs, endTime: endMs } }),
  });
  if (!res.ok) throw new Error(`Hyperliquid answered ${res.status}`);
  const rows = (await res.json()) as { t: number; c: string }[];
  return Array.isArray(rows) ? rows.map((r) => ({ t: Number(r.t), c: Number(r.c) })).filter((b) => Number.isFinite(b.c)) : [];
}

// ---- Catch-up trade: at the reopen, trade from CME's open toward where Hyperliquid is ----

/** Smallest gap between CME's open and the purple dot that makes a trade (points), per market. */
export const CATCH_UP_MIN: Record<string, number> = { NQ: 10, MNQ: 10 };
export const CATCH_UP_HOLD_MIN = 60;

export interface CatchUp {
  dir: 1 | -1;
  entry: number;
  target: number;
  stop: number;
  dist: number;
  exitT: number;
  how: 'target' | 'stop' | 'time';
  pts: number;
}

/**
 * Enter at CME's first price after the closure, aim for the purple dot, stop the same distance the
 * other way, out after an hour. The stop wins when both are touched in one bar.
 */
export function catchUp(nap: NapResult, candles: readonly { timestamp_ms: number; high: number; low: number; close: number }[], minGap: number): CatchUp | null {
  if (nap.hlAtOpen === null) return null;
  const gap = nap.hlAtOpen - nap.openPx;
  const dist = Math.abs(gap);
  if (dist < minGap) return null;
  const dir: 1 | -1 = gap > 0 ? 1 : -1;
  const entry = nap.openPx;
  const target = nap.hlAtOpen;
  const stop = entry - dir * dist;
  const end = nap.openT + CATCH_UP_HOLD_MIN * 60_000;
  let last: { timestamp_ms: number; close: number } | null = null;
  for (const c of candles) {
    if (c.timestamp_ms < nap.openT) continue;
    if (c.timestamp_ms >= end) break;
    last = c;
    const hi = Number(c.high); const lo = Number(c.low);
    if (dir > 0 ? lo <= stop : hi >= stop) return { dir, entry, target, stop, dist, exitT: c.timestamp_ms, how: 'stop', pts: -dist };
    if (dir > 0 ? hi >= target : lo <= target) return { dir, entry, target, stop, dist, exitT: c.timestamp_ms, how: 'target', pts: dist };
  }
  if (!last) return null;
  return { dir, entry, target, stop, dist, exitT: last.timestamp_ms, how: 'time', pts: (Number(last.close) - entry) * dir };
}
