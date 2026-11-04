import type { IndicatorDataPoint } from '@/types/contracts';

import { formatClock, formatPrice } from './alnGuide';

export interface TbrGuideStep {
  label: string;
  state: 'done' | 'current' | 'todo';
}

export interface TbrGuideView {
  sentence: string;
  /** Where price sits in the box it is in now, in plain words. */
  detail: string;
  tone: 'waiting' | 'live' | 'warn' | 'done';
  steps: TbrGuideStep[];
}

type Rates = Record<string, [number, number]>;

const num = (point: IndicatorDataPoint | null | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const NEW_YORK_HOUR = new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'America/New_York' });

function steps(at: number): TbrGuideStep[] {
  return ['Open', 'Hit ±0.25', 'Stretch', 'Back to open', 'Follow-through'].map((label, i) => ({
    label,
    state: i < at ? 'done' : i === at ? 'current' : 'todo',
  }));
}

/** Where `distance` (from the open, in the box's direction) sits among the box's median / P75 / P90. */
function place(distance: number, median: number, p75: number, p90: number): 0 | 1 | 2 | 3 {
  if (distance >= p90) return 3;
  if (distance >= p75) return 2;
  if (distance >= median) return 1;
  return 0;
}

/**
 * The AM TBR walk-through for the latest point: what happened this morning and where
 * price sits against the past days. It never says buy or sell.
 */
export function buildTbrGuideView(
  point: IndicatorDataPoint | null,
  rates: Rates,
  timeZone: string,
  options: { label?: string; startHour?: number } = {},
): TbrGuideView | null {
  const name = options.label ?? 'AM TBR';
  const startHour = options.startHour ?? 8;
  const open = num(point, 'open');
  if (point === null || open === null) return null;
  const up = num(point, '+0.25');
  const dn = num(point, '-0.25');
  const side = num(point, 'touch_side');
  const touchAt = num(point, 'touch_at');
  const clock = (ms: number): string => formatClock(ms, timeZone);

  if (side === null || touchAt === null) {
    return {
      sentence: `${name} Open ${formatPrice(open)}. Waiting for price to touch +0.25${up !== null ? ` (${formatPrice(up)})` : ''} or −0.25${dn !== null ? ` (${formatPrice(dn)})` : ''}.`,
      detail: 'Almost every session touches one of them, most often in the first hour.',
      tone: 'waiting',
      steps: steps(1),
    };
  }

  const sign = side > 0 ? '+' : '−';
  const hour = (Number(NEW_YORK_HOUR.format(new Date(touchAt))) - startHour + 24) % 24;
  const rate = rates[`${side},${hour}`];
  const odds = rate
    ? `Sessions like this came back to the ${name} Open ${Math.round(rate[0])}% of the time${rate[1] < 30 ? ' (few past days)' : ''}.`
    : 'Few past sessions touched this late.';
  const hit = `${sign}0.25 hit at ${clock(touchAt)}.`;
  const revertAt = num(point, 'revert_at');

  if (revertAt === null) {
    const now = num(point, 'stretch_now');
    const near = num(point, 'stretch_near');
    const mid = num(point, 'stretch_mid');
    const far = num(point, 'stretch_far');
    const line = side > 0 ? up : dn;
    let detail = 'Watching for the return to the open.';
    let tone: TbrGuideView['tone'] = 'live';
    if (now !== null && near !== null && mid !== null && far !== null && line !== null) {
      const d = (v: number): number => side * (v - open);
      const pts = Math.abs(now - line).toFixed(2);
      const at = place(d(now), d(near), d(mid), d(far));
      detail = [
        `Stretch so far ${pts} pts past the line, short of the median: half of comeback days stretch further.`,
        `Stretch ${pts} pts past the line, between the median and P75: a normal stretch.`,
        `Stretch ${pts} pts past the line, past P75: deeper than 3 in 4 comeback days.`,
        `Stretch ${pts} pts past the line, past P90: deeper than 9 in 10 comeback days. This is starting to look like a no-return day (red box).`,
      ][at];
      if (at === 3) tone = 'warn';
    }
    return { sentence: `${hit} ${odds}`, detail, tone, steps: steps(2) };
  }

  const now = num(point, 'follow_now');
  const near = num(point, 'follow_near');
  const mid = num(point, 'follow_mid');
  const far = num(point, 'follow_far');
  let detail = 'Watching the follow-through past the open.';
  if (now !== null && near !== null && mid !== null && far !== null) {
    const d = (v: number): number => -side * (v - open);
    const pts = Math.max(0, d(now)).toFixed(2);
    detail = [
      `Follow-through so far ${pts} pts past the open, short of the median: half of comeback days go further.`,
      `Follow-through ${pts} pts past the open, past the median: further than half of comeback days.`,
      `Follow-through ${pts} pts past the open, past P75: further than 3 in 4 comeback days.`,
      `Follow-through ${pts} pts past the open, past P90: further than 9 in 10 comeback days.`,
    ][place(d(now), d(near), d(mid), d(far))];
  }
  return {
    sentence: `${hit} Back at the ${name} Open at ${clock(revertAt)} ✓`,
    detail,
    tone: 'done',
    steps: steps(4),
  };
}

/** New York hour each ALN TBR session opens. */
export const TBR_SESSION_START_HOUR: Record<string, number> = { cme: 18, asia: 20, ldn: 2, am: 8, pm: 12, ny: 8 };

const SESSION_FIELDS: [string, string][] = [
  ['open', 'open'], ['+0.25', 'up'], ['-0.25', 'dn'], ['touch_side', 'side'], ['touch_at', 'touch_at'],
  ['revert_at', 'revert_at'], ['stretch_near', 'stretch_near'], ['stretch_mid', 'stretch_mid'],
  ['stretch_far', 'stretch_far'], ['follow_near', 'follow_near'], ['follow_mid', 'follow_mid'],
  ['follow_far', 'follow_far'], ['stretch_now', 'stretch_now'], ['follow_now', 'follow_now'],
];

export interface ActiveTbrSession {
  key: string;
  label: string;
  /** The session's fields under the AM TBR names buildTbrGuideView reads. */
  point: IndicatorDataPoint;
}

/** The ALN TBR session drawn at the most recent point (the live one, or the last one that ran). */
export function activeTbrSession(
  points: readonly IndicatorDataPoint[],
  sessions: readonly { key: string; label: string }[],
  lookback = 3000,
): ActiveTbrSession | null {
  for (let i = points.length - 1; i >= Math.max(0, points.length - lookback); i -= 1) {
    const p = points[i];
    // Several sessions can overlap (NY with AM / PM): the one that opened last wins.
    let best: { key: string; label: string } | null = null;
    let bestStart = -Infinity;
    for (const s of sessions) {
      if (num(p, `${s.key}_open`) === null) continue;
      const start = TBR_SESSION_START_HOUR[s.key] ?? 0;
      const nyHour = Number(NEW_YORK_HOUR.format(new Date(Number(p.timestamp_ms))));
      const since = (nyHour - start + 24) % 24;
      if (-since > bestStart) {
        best = s;
        bestStart = -since;
      }
    }
    if (best) {
      const point: IndicatorDataPoint = { timestamp_ms: p.timestamp_ms };
      for (const [to, from] of SESSION_FIELDS) {
        const v = num(p, `${best.key}_${from}`);
        if (v !== null) point[to] = v;
      }
      return { key: best.key, label: best.label, point };
    }
  }
  return null;
}
