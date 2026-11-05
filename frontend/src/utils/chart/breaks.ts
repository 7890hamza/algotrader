import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import { formatClock, formatPrice, type SessionTag } from './alnGuide';

/** ES 2016-2025 odds for the Breaks indicator (see indicator-api BREAK_RATES). */
export interface BreakRates {
  rth: {
    inside: { n: number; either: number; one: number; both: number; upper: [number, number]; middle: [number, number]; lower: [number, number] };
    gap_up: { n: number; held: number };
    gap_down: { n: number; held: number };
  };
  ib: { n: number; either: number; above: [number, number, number]; below: [number, number, number]; ext: [number, number] };
  eth: { inside: { n: number; either: number; upper: [number, number]; middle: [number, number]; lower: [number, number] } };
}

export function readBreaksGuide(guide: JsonObject | undefined): BreakRates | null {
  if (!guide || guide.kind !== 'breaks' || typeof guide.rates !== 'object' || guide.rates === null) return null;
  return guide.rates as unknown as BreakRates;
}

const NY_PARTS = new Intl.DateTimeFormat('en-US', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: 'numeric', minute: '2-digit', hourCycle: 'h23', timeZone: 'America/New_York',
});
const CHIP_BG = 'rgba(139, 148, 158, 0.22)';
const CHIP_FG = '#c9d1d9';
const IB_BG = 'rgba(76, 155, 232, 0.2)';
const IB_FG = '#7db8f0';
const ETH_BG = 'rgba(180, 154, 240, 0.18)';
const ETH_FG = '#c7b5f5';
const RTH_END = 16 * 60;
const ETH_END = 17 * 60;

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

function newYork(ms: number): { date: string; minute: number } {
  const parts = Object.fromEntries(NY_PARTS.formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minute: Number(parts.hour) * 60 + Number(parts.minute) };
}

/** 78.6 -> 8 ("8 in 10") */
export const inTen = (pct: number): number => Math.round(pct / 10);

const missLine = (pct: number): string => {
  const miss = 10 - inTen(pct);
  return `So about ${miss} ${miss === 1 ? 'day' : 'days'} in 10 it doesn't happen`;
};

const pctText = (pct: number): string => `${pct.toFixed(0)}% of the time (${inTen(pct)} in 10)`;

/** Consecutive points that share the same values for `keys` (one session each). */
function runs(points: readonly IndicatorDataPoint[], keys: string[], present: string): IndicatorDataPoint[][] {
  const out: IndicatorDataPoint[][] = [];
  let run: IndicatorDataPoint[] = [];
  for (const point of points) {
    if (num(point, present) === null) {
      if (run.length) out.push(run);
      run = [];
      continue;
    }
    const prev = run[run.length - 1];
    const same = prev !== undefined && keys.every((k) => num(prev, k) === num(point, k))
      && Number(point.timestamp_ms) - Number(prev.timestamp_ms) < 4 * 3_600_000;
    if (!same && run.length) {
      out.push(run);
      run = [];
    }
    run.push(point);
  }
  if (run.length) out.push(run);
  return out;
}

function barMinutes(points: readonly IndicatorDataPoint[]): number {
  let smallest = Number.POSITIVE_INFINITY;
  for (let i = 1; i < points.length; i += 1) {
    const diff = Number(points[i].timestamp_ms) - Number(points[i - 1].timestamp_ms);
    if (diff > 0 && diff < smallest) smallest = diff;
  }
  return Number.isFinite(smallest) ? Math.max(1, Math.round(smallest / 60_000)) : 1;
}

interface Bet {
  /** What the chip says is likely, e.g. "pRTH low gets hit". */
  phrase: string;
  pct: number;
  /** 'hit' = the likely thing is a hit; 'held' = the likely thing is no hit. */
  kind: 'hit' | 'held' | 'any';
  line: 'h' | 'l' | null;
}

function result(bet: Bet, hitH: boolean, hitL: boolean, finished: boolean): SessionTag['result'] {
  if (bet.kind === 'held') {
    const broke = bet.line === 'h' ? hitH : hitL;
    return broke ? 'missed' : finished ? 'reached' : 'none';
  }
  const done = bet.kind === 'any' ? hitH || hitL : bet.line === 'h' ? hitH : hitL;
  return done ? 'reached' : finished ? 'missed' : 'none';
}

function hitLines(name: string, run: IndicatorDataPoint[], hKey: string, lKey: string, timeZone: string, finished: boolean, end: string): string[] {
  const last = run[run.length - 1];
  const out: string[] = [];
  const h = num(last, hKey);
  const l = num(last, lKey);
  if (h !== null) out.push(`${name} high hit at ${formatClock(h, timeZone)}`);
  if (l !== null) out.push(`${name} low hit at ${formatClock(l, timeZone)}`);
  if (!out.length) out.push(finished ? `Neither line was hit by ${end}` : 'Neither line is hit yet');
  return out;
}

function thirdBet(name: string, third: number, odds: { either: number; upper: [number, number]; middle: [number, number]; lower: [number, number] }): Bet {
  if (third > 0) return { phrase: `${name} high gets hit`, pct: odds.upper[0], kind: 'hit', line: 'h' };
  if (third < 0) return { phrase: `${name} low gets hit`, pct: odds.lower[1], kind: 'hit', line: 'l' };
  return { phrase: 'One side usually gets hit', pct: odds.either, kind: 'any', line: null };
}

const THIRDS: Record<string, string> = { '1': 'upper third', '0': 'middle third', '-1': 'lower third' };

function chipText(bet: Bet): string {
  return bet.kind === 'any' ? `${bet.phrase} · ${inTen(bet.pct)} in 10` : `Likely: ${bet.phrase} · ${inTen(bet.pct)} in 10`;
}

function thirdLines(name: string, word: string, third: number, odds: { n: number; either: number; upper: [number, number]; middle: [number, number]; lower: [number, number] }): string[] {
  const key = third > 0 ? 'upper' : third < 0 ? 'lower' : 'middle';
  const [h, l] = odds[key];
  const lines = [`Opened inside ${word}, in the ${THIRDS[String(third)]}`];
  if (third === 0) {
    lines.push(`On days like this, at least one side got hit ${pctText(odds.either)}`);
    lines.push(`No side is favored: high ${h.toFixed(0)}%, low ${l.toFixed(0)}%`);
  } else {
    const fav = third > 0 ? h : l;
    lines.push(`On days like this, the ${name} ${third > 0 ? 'high' : 'low'} got hit ${pctText(fav)}`);
    lines.push(`The ${third > 0 ? 'low' : 'high'} side: ${(third > 0 ? l : h).toFixed(0)}%`);
  }
  return lines;
}

/**
 * One chip per session: what's likely today in plain words ("Likely: pRTH low gets hit · 8 in 10"),
 * a ✓ / ✕ once it settles, and a plain recap on hover.
 */
export function buildBreaksTags(points: readonly IndicatorDataPoint[], rates: BreakRates, timeZone: string): SessionTag[] {
  const sorted = [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)))
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  if (!sorted.length) return [];
  const lastPoint = sorted[sorted.length - 1];
  const bar = barMinutes(sorted);
  const day = (ms: number): string => new Date(ms).toLocaleDateString('en-US', { weekday: 'short', timeZone });
  const tags: SessionTag[] = [];
  const finishedBy = (run: IndicatorDataPoint[], endMinute: number): boolean => {
    const last = run[run.length - 1];
    if (last !== lastPoint) return true;
    const m = newYork(Number(last.timestamp_ms)).minute;
    return m + bar >= endMinute && m < endMinute + 60;
  };
  const base = (id: string, run: IndicatorDataPoint[], top: number, bg: string, fg: string): SessionTag => ({
    id,
    startTime: Math.floor(Number(run[0].timestamp_ms) / 1000),
    endTime: Math.floor(Number(run[run.length - 1].timestamp_ms) / 1000),
    top,
    date: day(Number(run[0].timestamp_ms)),
    pattern: 2,
    lines: [],
    result: 'none',
    chipBg: bg,
    chipFg: fg,
  });

  for (const run of runs(sorted, ['prth_h', 'prth_l'], 'prth_h')) {
    const first = run[0];
    const last = run[run.length - 1];
    const ph = num(first, 'prth_h')!;
    const pl = num(first, 'prth_l')!;
    const setup = num(first, 'rth_setup');
    const finished = finishedBy(run, RTH_END);
    let top = ph;
    for (const p of run) for (const k of ['ib_box_h', 'ib_h']) { const v = num(p, k); if (v !== null && v > top) top = v; }
    const tag = base(`breaks-rth@${first.timestamp_ms}`, run, top, CHIP_BG, CHIP_FG);
    const hitH = num(last, 'rth_hit_h') !== null;
    const hitL = num(last, 'rth_hit_l') !== null;
    let bet: Bet;
    let n: number;
    if (setup === 1 || setup === -1) {
      const odds = setup === 1 ? rates.rth.gap_up : rates.rth.gap_down;
      const side = setup === 1 ? 'low' : 'high';
      bet = { phrase: `pRTH ${side} stays untouched`, pct: odds.held, kind: 'held', line: setup === 1 ? 'l' : 'h' };
      n = odds.n;
      tag.lines = [
        `Opened ${setup === 1 ? 'above' : 'below'} yesterday's RTH ${setup === 1 ? 'high' : 'low'} ${formatPrice(setup === 1 ? ph : pl)}`,
        `On days like this, yesterday's ${side} ${formatPrice(setup === 1 ? pl : ph)} stayed untouched ${pctText(odds.held)}`,
      ];
    } else {
      const third = num(first, 'rth_third') ?? 0;
      bet = thirdBet('pRTH', third, rates.rth.inside);
      n = rates.rth.inside.n;
      tag.lines = thirdLines('pRTH', "yesterday's RTH range", third, rates.rth.inside);
    }
    tag.chipText = chipText(bet);
    tag.result = result(bet, hitH, hitL, finished);
    tag.lines.push(missLine(bet.pct));
    tag.lines.push(...hitLines('pRTH', run, 'rth_hit_h', 'rth_hit_l', timeZone, finished, 'the close'));
    tag.lines.push(`Odds: ES 2016-2025, ${n.toLocaleString()} days like this. A hit = 1 tick past the line.`);
    tags.push(tag);
  }

  // IB: the chip sits over the IB box; the story covers the rest of the day.
  const byDay = new Map<string, IndicatorDataPoint[]>();
  for (const p of sorted) {
    if (num(p, 'ib_box_h') === null && num(p, 'ib_h') === null) continue;
    const key = newYork(Number(p.timestamp_ms)).date;
    const list = byDay.get(key) ?? [];
    list.push(p);
    byDay.set(key, list);
  }
  for (const run of byDay.values()) {
    const box = run.filter((p) => num(p, 'ib_box_h') !== null);
    if (!box.length) continue;
    const post = run.filter((p) => num(p, 'ib_h') !== null);
    const top = Math.max(...box.map((p) => num(p, 'ib_box_h')!));
    const tag = base(`breaks-ib@${box[0].timestamp_ms}`, box, top, IB_BG, IB_FG);
    tag.date = 'IB';
    tag.anchor = 'start';
    if (!post.length) {
      tag.chipText = 'forming';
      tag.lines = ['The first hour is still setting the IB high and low', `About ${inTen(rates.ib.either)} in 10 days break at least one side later`];
      tags.push(tag);
      continue;
    }
    const p0 = post[0];
    const last = post[post.length - 1];
    const finished = finishedBy(post, RTH_END);
    const side = num(p0, 'ib_side') ?? 0;
    const ibh = num(p0, 'ib_h')!;
    const ibl = num(p0, 'ib_l')!;
    const hitH = num(last, 'ib_hit_h') !== null;
    const hitL = num(last, 'ib_hit_l') !== null;
    if (num(p0, 'ib_valid') !== 1) {
      tag.chipText = 'no setup';
      tag.lines = ['The bar after the IB opened outside it, so today is not in the stats'];
    } else if (side === 0) {
      tag.chipText = 'no favorite';
      tag.lines = ['The IB closed right on its middle, so neither side is favored'];
    } else {
      const odds = side > 0 ? rates.ib.above : rates.ib.below;
      const bet: Bet = side > 0
        ? { phrase: 'IB high gets hit', pct: odds[0], kind: 'hit', line: 'h' }
        : { phrase: 'IB low gets hit', pct: odds[1], kind: 'hit', line: 'l' };
      tag.chipText = chipText(bet);
      tag.result = result(bet, hitH, hitL, finished);
      tag.lines = [
        `The IB (${formatPrice(ibl)} to ${formatPrice(ibh)}, ${formatPrice(ibh - ibl)} pts) closed in its ${side > 0 ? 'top' : 'bottom'} half`,
        `On days like this, the IB ${side > 0 ? 'high' : 'low'} got hit ${pctText(side > 0 ? odds[0] : odds[1])}`,
        `The other side: ${(side > 0 ? odds[1] : odds[0]).toFixed(0)}%`,
        missLine(bet.pct),
      ];
    }
    tag.lines.push(...hitLines('IB', post, 'ib_hit_h', 'ib_hit_l', timeZone, finished, 'the close'));
    const med = num(last, 'ib_ext_med');
    const p75 = num(last, 'ib_ext_p75');
    if (med !== null && p75 !== null) tag.lines.push(`After the break, half of days reach ${formatPrice(med)}, 1 in 4 reach ${formatPrice(p75)}`);
    tags.push(tag);
  }

  for (const run of runs(sorted, ['peth_h', 'peth_l'], 'peth_h')) {
    const first = run[0];
    const last = run[run.length - 1];
    const finished = finishedBy(run, ETH_END);
    const tag = base(`breaks-eth@${first.timestamp_ms}`, run, num(first, 'peth_h')!, ETH_BG, ETH_FG);
    tag.date = 'ETH';
    const setup = num(first, 'eth_setup');
    if (setup !== 0) {
      tag.chipText = 'opened outside';
      tag.lines = ["The 3 PM open was outside yesterday's full-session range. That's rare (about 7% of days), so there are no odds."];
    } else {
      const third = num(first, 'eth_third') ?? 0;
      const bet = thirdBet('pETH', third, rates.eth.inside);
      tag.chipText = chipText(bet);
      tag.result = result(bet, num(last, 'eth_hit_h') !== null, num(last, 'eth_hit_l') !== null, finished);
      tag.lines = thirdLines('pETH', "yesterday's full session (3 PM to 2 PM)", third, rates.eth.inside);
      tag.lines.push(missLine(bet.pct));
    }
    tag.lines.push(...hitLines('pETH', run, 'eth_hit_h', 'eth_hit_l', timeZone, finished, '2 PM'));
    tags.push(tag);
  }
  return tags;
}

/** Past sessions keep their lines and Hit arrows without text; the running one gets small labels. */
export function tidyBreakSegments<T extends { endTime: number; label: string; showPrice: boolean; labelColor: string; compact?: boolean; touchText?: string }>(
  segments: readonly T[],
  lastTime: number,
): T[] {
  return segments.map((s) =>
    s.endTime === lastTime
      ? { ...s, compact: true, labelColor: '#9aa4b2' }
      : { ...s, label: '', showPrice: false, touchText: undefined },
  );
}

/** MTF SDEV: only the running candle's lines keep their labels; older ones stay as plain lines. */
export function quietPastSegments<T extends { endTime: number; label: string; showPrice: boolean; touchText?: string }>(
  segments: readonly T[],
  lastTime: number,
): T[] {
  return segments.map((s) => (s.endTime === lastTime ? s : { ...s, label: '', showPrice: false, touchText: undefined }));
}

/**
 * MTF SDEV layout: by default only the running candles' lines are drawn, and the weekly /
 * monthly lines (and PWH / PWL) are short stubs just left of price. With past days on, earlier
 * lines stay as plain unlabeled lines.
 */
export function mtfLayout<T extends { id: string; startTime: number; endTime: number; label: string; showPrice: boolean; touchText?: string }>(
  segments: readonly T[],
  lastTime: number,
  options: { pastDays: boolean; stubSeconds: number },
): T[] {
  if (options.pastDays) return quietPastSegments(segments, lastTime);
  return segments
    .filter((s) => s.endTime === lastTime)
    .map((s) => (/^(w_|m_|pwh|pwl)/.test(s.id) ? { ...s, startTime: Math.max(s.startTime, lastTime - options.stubSeconds) } : s));
}
