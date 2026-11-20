import type { IndicatorDataPoint } from '@/types/contracts';

/**
 * The seven setups from the 2026 ES backtest (engine: indicators/setups.py). The engine returns
 * one row per trade start; this turns those rows into trades and groups them by CME trading day.
 */

export type SetupId = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

export interface SetupInfo {
  id: SetupId;
  dir: 1 | -1;
  name: string;
  why: string;
  levels: [string, string | null];
}

export const SETUPS: SetupInfo[] = [
  { id: 'A', dir: 1, name: 'Double high break', levels: ['Yesterday RTH high', 'Last week high'],
    why: 'Price pushed above yesterday’s regular-hours high while already above last week’s high. Two highs broken at once: buyers in control.' },
  { id: 'B', dir: 1, name: 'Quick push on a calm day', levels: ['Day open', null],
    why: 'The 15-minute candle broke its last high while the daily candle was already pushing up inside yesterday’s range.' },
  { id: 'C', dir: 1, name: 'Month up, AM dip reclaimed', levels: ['AM range open', 'Month open'],
    why: 'Above the month’s open, the morning dipped below its 8 AM open and came back to it. The dip failed, so price went up.' },
  { id: 'D', dir: -1, name: 'Day stretched down, hour breaks low', levels: ['Day −1 SD', 'Last hour low'],
    why: 'Price was already a full SDEV below the day’s open and then broke the last hour’s low without coming back.' },
  { id: 'E', dir: -1, name: '4H breakdown + NY stretched down', levels: ['NY −1 SD', null],
    why: 'The 4-hour candle broke the last 4-hour low and New York was already a full SDEV below its open.' },
  { id: 'F', dir: -1, name: 'Below yesterday’s low, AM pop failed', levels: ['AM range open', 'Yesterday low'],
    why: 'Below yesterday’s low, the morning popped above its 8 AM open and fell back to it. The pop failed, so price went down.' },
  { id: 'G', dir: -1, name: 'Spike up fails below yesterday’s low', levels: ['Hour +1.5σ', 'Yesterday low'],
    why: 'Price spiked more than 1.5σ above the hour’s open while still under yesterday’s low. Spikes like that tend to snap back.' },
];

export const SETUP_BY_ID = Object.fromEntries(SETUPS.map((s) => [s.id, s])) as Record<SetupId, SetupInfo>;

export interface SetupTrade {
  id: SetupId;
  dir: 1 | -1;
  entryMs: number;
  exitMs: number;
  entry: number;
  pts: number;
  how: 'target' | 'stop' | 'time';
  levels: { name: string; price: number }[];
  day: string; // CME trading day (6 PM to 5 PM New York), YYYY-MM-DD
}

const num = (p: IndicatorDataPoint, k: string): number | null => {
  const v = p[k];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
};

const dayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });

/** CME trading day of an instant: anything from 6 PM New York on belongs to the next day. */
export function cmeDay(ms: number): string {
  return dayFmt.format(new Date(ms + 6 * 3_600_000));
}

export function tradesFrom(points: readonly IndicatorDataPoint[]): SetupTrade[] {
  const trades: SetupTrade[] = [];
  for (const p of points) {
    const entryMs = Number(p.timestamp_ms);
    for (const s of SETUPS) {
      const dir = num(p, `${s.id}_dir`);
      const entry = num(p, `${s.id}_entry`);
      if (dir === null || entry === null) continue;
      const how = num(p, `${s.id}_how`);
      const levels = s.levels
        .map((name, i) => ({ name, price: num(p, `${s.id}_l${i + 1}`) }))
        .filter((l): l is { name: string; price: number } => l.name !== null && l.price !== null);
      trades.push({
        id: s.id, dir: dir > 0 ? 1 : -1, entryMs, exitMs: num(p, `${s.id}_exit_ms`) ?? entryMs, entry,
        pts: num(p, `${s.id}_pts`) ?? 0, how: how === 1 ? 'target' : how === -1 ? 'stop' : 'time',
        levels, day: cmeDay(entryMs),
      });
    }
  }
  return trades.sort((a, b) => a.entryMs - b.entryMs);
}

export interface SetupScore { id: SetupId; trades: number; hitRate: number; pts: number }

export function scoreSetups(trades: readonly SetupTrade[]): SetupScore[] {
  return SETUPS.map((s) => {
    const mine = trades.filter((t) => t.id === s.id);
    return {
      id: s.id,
      trades: mine.length,
      hitRate: mine.length ? mine.filter((t) => t.how === 'target').length / mine.length : 0,
      pts: Math.round(mine.reduce((a, t) => a + t.pts, 0) * 100) / 100,
    };
  });
}

/** CME day start (6 PM New York the evening before) and end (5 PM) in epoch ms. */
export function cmeDayBounds(day: string): { startMs: number; endMs: number } {
  const noonUtc = Date.parse(`${day}T12:00:00Z`);
  const offsetH = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' })
    .format(new Date(noonUtc)));
  const nyOffset = (offsetH - 12) * 3_600_000; // -4 h or -5 h
  const midnight = Date.parse(`${day}T00:00:00Z`) - nyOffset;
  return { startMs: midnight - 6 * 3_600_000, endMs: midnight + 17 * 3_600_000 };
}

// ---- Stacked stats: where several Game Plan levels sit (or got hit) at about the same price ----

export interface StatLevel { label: string; price: number; odds: number | null; hitAt: number | null; frm: number; until: number; never: boolean }

export interface HitStack {
  from: number; to: number; lo: number; hi: number; count: number; labels: string[];
  /** +1: price came down into it (reverting means up), -1: came up into it. */
  approach: 1 | -1;
  back: number | null; further: number | null;
}

export interface OpenStack { lo: number; hi: number; count: number; labels: string[]; away: number }

/** Several levels hit within `width` points of each other and `gapMs` of each other. */
export function hitStacks(
  levels: readonly StatLevel[], candles: readonly { time: number; high: number; low: number; close: number }[],
  width: number, minCount: number, gapMs = 15 * 60_000, holdMs = 60 * 60_000,
): HitStack[] {
  const hits = levels.filter((l) => !l.never && l.hitAt !== null).sort((a, b) => (a.hitAt as number) - (b.hitAt as number));
  const groups: StatLevel[][] = [];
  for (const h of hits) {
    const g = groups[groups.length - 1];
    const prices = g?.map((x) => x.price) ?? [];
    if (g && (h.hitAt as number) - (g[g.length - 1].hitAt as number) <= gapMs
      && Math.max(...prices, h.price) - Math.min(...prices, h.price) <= width) g.push(h);
    else groups.push([h]);
  }
  return groups.filter((g) => g.length >= minCount).map((g) => {
    const from = g[0].hitAt as number; const to = g[g.length - 1].hitAt as number;
    const lo = Math.min(...g.map((x) => x.price)); const hi = Math.max(...g.map((x) => x.price));
    const before = candles.filter((c) => c.time * 1000 < from && c.time * 1000 >= from - 30 * 60_000);
    const approach: 1 | -1 = before.length && before[0].close > (lo + hi) / 2 ? 1 : -1;
    const after = candles.filter((c) => c.time * 1000 >= to && c.time * 1000 < to + holdMs);
    const mid = (lo + hi) / 2;
    const back = after.length ? (approach > 0 ? Math.max(...after.map((c) => c.high)) - mid : mid - Math.min(...after.map((c) => c.low))) : null;
    const further = after.length ? Math.max(0, approach > 0 ? lo - Math.min(...after.map((c) => c.low)) : Math.max(...after.map((c) => c.high)) - hi) : null;
    return { from, to, lo, hi, count: g.length, labels: g.map((x) => x.label), approach, back, further };
  });
}

/** Levels still open at time t that sit within `width` points of each other, nearest first. */
export function openStacks(levels: readonly StatLevel[], t: number, price: number, width: number, minCount: number): OpenStack[] {
  const open = levels
    .filter((l) => !l.never && l.frm <= t && t < l.until && (l.hitAt === null || l.hitAt > t))
    .sort((a, b) => a.price - b.price);
  const out: OpenStack[] = [];
  let i = 0;
  while (i < open.length) {
    let j = i;
    while (j + 1 < open.length && open[j + 1].price - open[i].price <= width) j++;
    const g = open.slice(i, j + 1);
    if (g.length >= minCount) {
      const lo = g[0].price; const hi = g[g.length - 1].price;
      out.push({ lo, hi, count: g.length, labels: g.map((x) => `${x.label}${x.odds !== null ? ` ${Math.round(x.odds)}%` : ''}`),
        away: Math.round((price > hi ? price - hi : lo > price ? lo - price : 0) * 4) / 4 });
      i = j + 1;
    } else i++;
  }
  return out.sort((a, b) => a.away - b.away);
}

// ---- Drawing trades on the regular chart ----

/** Dollars per point for one contract. */
export const POINT_VALUE: Record<string, number> = { ES: 50, MES: 5, NQ: 20, MNQ: 2 };

/**
 * Target (green) and stop (red) boxes from entry to exit. The result is left off the chart on
 * purpose, so a replay doesn't give it away; the Setups panel shows it once the trade is done.
 */
export function setupBoxes(trades: readonly SetupTrade[], target = 10, stop = 3): import('./chart/alnGuide').SessionBox[] {
  const out: import('./chart/alnGuide').SessionBox[] = [];
  for (const t of trades) {
    const s = SETUP_BY_ID[t.id];
    const startTime = Math.floor(t.entryMs / 1000);
    const endTime = Math.max(startTime, Math.floor(t.exitMs / 1000));
    const tgt = t.entry + target * t.dir; const stp = t.entry - stop * t.dir;
    const hover = [`${t.id} ${t.dir > 0 ? 'long' : 'short'} · ${s.name}`, s.why, `Entry ${t.entry.toFixed(2)} · target ${tgt.toFixed(2)} · stop ${stp.toFixed(2)}`];
    out.push({ id: `setup-${t.id}-${startTime}-t`, startTime, endTime, high: Math.max(t.entry, tgt), low: Math.min(t.entry, tgt),
      color: '#2fbf8f', label: '', fillOpacity: 0.22, noLabels: true, title: `${t.id} ${t.dir > 0 ? '▲' : '▼'}`, hoverLines: hover });
    out.push({ id: `setup-${t.id}-${startTime}-s`, startTime, endTime, high: Math.max(t.entry, stp), low: Math.min(t.entry, stp),
      color: '#e0566c', label: '', fillOpacity: 0.28, noLabels: true, hoverLines: hover });
  }
  return out;
}
