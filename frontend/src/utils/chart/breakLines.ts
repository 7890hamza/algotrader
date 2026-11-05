import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import { formatClock, formatPrice, type SessionBox, type SessionTag } from './alnGuide';
import { type BreakRates, buildBreaksTags, tidyBreakSegments } from './breaks';
import { buildRetrace, type RetraceLayer } from './retrace';
import type { SessionLevelSegment } from './sessionLevels';

const NY_TIME = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hourCycle: 'h23', timeZone: 'America/New_York' });
const RTH_OPEN = 9 * 60 + 30;
const RTH_END = 16 * 60;

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

function nyMinute(ms: number): number {
  const [h, m] = NY_TIME.format(new Date(ms)).split(':').map(Number);
  return h * 60 + m;
}

const pct = (p: number): string => `${Math.round(p)}%`;
const THIRD: Record<string, 'upper' | 'middle' | 'lower'> = { '1': 'upper', '0': 'middle', '-1': 'lower' };

interface Notes {
  h?: string;
  l?: string;
  extra?: string[];
}

function rthNotes(first: IndicatorDataPoint, last: IndicatorDataPoint, rates: BreakRates, finished: boolean): Notes {
  const setup = num(first, 'rth_setup');
  const hitH = num(last, 'rth_hit_h') !== null;
  const hitL = num(last, 'rth_hit_l') !== null;
  if (setup === 1) return { l: `${pct(rates.rth.gap_up.held)} holds${hitL ? ' ✗' : finished ? ' ✓' : ''}` };
  if (setup === -1) return { h: `${pct(rates.rth.gap_down.held)} holds${hitH ? ' ✗' : finished ? ' ✓' : ''}` };
  const odds = rates.rth.inside[THIRD[String(num(first, 'rth_third') ?? 0)]];
  return {
    h: `${pct(odds[0])} to get hit${hitH ? ' ✓' : ''}`,
    l: `${pct(odds[1])} to get hit${hitL ? ' ✓' : ''}`,
  };
}

/** pETH notes change at 6:30 AM PT: what overnight already hit decides what is left. */
function ethNotes(run: readonly IndicatorDataPoint[], rates: BreakRates, finished: boolean): Notes {
  const first = run[0];
  const last = run[run.length - 1];
  if (num(first, 'eth_setup') !== 0) return {};
  const hitHAt = num(last, 'eth_hit_h');
  const hitLAt = num(last, 'eth_hit_l');
  const openPoint = run.find((p) => {
    const m = nyMinute(Number(p.timestamp_ms));
    return m >= RTH_OPEN && m < 17 * 60;
  });
  if (!openPoint) {
    const odds = rates.eth.inside[THIRD[String(num(first, 'eth_third') ?? 0)]];
    return {
      h: `${pct(odds[0])} to get hit${hitHAt !== null ? ' ✓' : ''}`,
      l: `${pct(odds[1])} to get hit${hitLAt !== null ? ' ✓' : ''}`,
    };
  }
  const openMs = Number(openPoint.timestamp_ms);
  const hBefore = hitHAt !== null && hitHAt < openMs;
  const lBefore = hitLAt !== null && hitLAt < openMs;
  const o = rates.eth.overnight;
  if (hBefore && lBefore) return { h: 'Hit overnight', l: 'Hit overnight' };
  if (hBefore || lBefore) {
    const otherHit = hBefore ? hitLAt !== null : hitHAt !== null;
    const held = `${pct(o.other_held)} holds${otherHit ? ' ✗' : finished ? ' ✓' : ''}`;
    return {
      h: hBefore ? 'Hit overnight' : held,
      l: lBefore ? 'Hit overnight' : held,
      extra: [`Overnight already hit the pETH ${hBefore ? 'high' : 'low'}. From there, the other side held ${pct(o.other_held)} of the time (${o.n_one.toLocaleString()} days).`],
    };
  }
  const either = `${pct(o.one_by_close)} one side by 2 PM${hitHAt !== null || hitLAt !== null ? ' ✓' : ''}`;
  return {
    h: either,
    l: either,
    extra: [`Neither line was hit overnight. From 6:30 AM, one got hit by 2 PM ${pct(o.one_by_close)} of the time (${o.n_none.toLocaleString()} days).`],
  };
}

/**
 * Writes the odds on the running pRTH / pETH lines and gives every pRTH / pETH line a hover
 * card (the same story the chips used to tell). `tags` are buildBreaksTags' RTH / ETH tags.
 */
export function annotateBreakLines(
  segments: readonly SessionLevelSegment[],
  points: readonly IndicatorDataPoint[],
  tags: readonly SessionTag[],
  rates: BreakRates,
): SessionLevelSegment[] {
  const sorted = [...points].sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  if (!sorted.length) return [...segments];
  const lastTime = Math.floor(Number(sorted[sorted.length - 1].timestamp_ms) / 1000);
  const byStart = new Map<string, SessionTag>();
  for (const t of tags) {
    if (t.id.startsWith('breaks-rth')) byStart.set(`rth@${t.startTime}`, t);
    else if (t.id.startsWith('breaks-eth')) byStart.set(`eth@${t.startTime}`, t);
  }
  const runOf = (start: number, end: number): IndicatorDataPoint[] =>
    sorted.filter((p) => { const t = Math.floor(Number(p.timestamp_ms) / 1000); return t >= start && t <= end; });
  return segments.map((s) => {
    const m = /^(prth|peth)_(h|l)@/.exec(s.id);
    if (!m) return s;
    const kind = m[1] === 'prth' ? 'rth' : 'eth';
    const tag = byStart.get(`${kind}@${s.startTime}`);
    const run = runOf(s.startTime, s.endTime);
    if (!run.length) return s;
    const last = run[run.length - 1];
    const lastMinute = nyMinute(Number(last.timestamp_ms));
    const notes = kind === 'rth'
      ? rthNotes(run[0], last, rates, lastMinute + 5 >= RTH_END)
      : ethNotes(run, rates, lastMinute + 5 >= 17 * 60 && lastMinute < 18 * 60);
    const hoverLines = [...(tag?.lines ?? [])];
    if (notes.extra) hoverLines.splice(Math.min(2, hoverLines.length), 0, ...notes.extra);
    const live = s.endTime === lastTime;
    const note = live ? (m[2] === 'h' ? notes.h : notes.l) : undefined;
    return { ...s, ...(note ? { note } : {}), ...(hoverLines.length ? { hoverLines } : {}) };
  });
}

/** Hover text for the see-through pRTH / pETH boxes. */
export function describeBreakBoxes(boxes: readonly SessionBox[], timeZone: string): SessionBox[] {
  return boxes.map((b) => {
    if (b.id.startsWith('rth_day@')) {
      return { ...b, hoverLines: [
        `pRTH box: this session's 6:30 AM–1 PM range (${formatClock(b.startTime * 1000, timeZone)} start)`,
        `${formatPrice(b.low)} to ${formatPrice(b.high)}`,
        'The next day carries these forward as the pRTH High / Low lines and checks where it opens against them.',
      ] };
    }
    if (b.id.startsWith('eth_day@')) {
      return { ...b, hoverLines: [
        "pETH box: this session's full 3 PM–2 PM range (overnight included)",
        `${formatPrice(b.low)} to ${formatPrice(b.high)}`,
        'The next day carries these forward as the pETH High / Low lines. Bigger than pRTH because it includes Asia and London.',
      ] };
    }
    return b;
  });
}

export interface BreaksLayout {
  segments: SessionLevelSegment[];
  boxes: SessionBox[];
  tags: SessionTag[];
  retrace: RetraceLayer | null;
}

/**
 * Everything Breaks draws: quiet past lines, odds notes and hover cards on the pRTH / pETH
 * lines, titled see-through pRTH / pETH boxes, the IB chip and the retracement layer.
 */
export function layoutBreaks(
  points: readonly IndicatorDataPoint[],
  segments: readonly SessionLevelSegment[],
  boxes: readonly SessionBox[],
  rates: BreakRates,
  guide: JsonObject | undefined,
  timeZone: string,
  lastTime: number,
): BreaksLayout {
  const tags = buildBreaksTags(points, rates, timeZone);
  const retrace = buildRetrace(points, guide, timeZone);
  // Only the IB box that is still forming keeps its labels.
  const quietBoxes = boxes.map((b) => (b.endTime === lastTime ? b : { ...b, noLabels: true }));
  return {
    segments: [...annotateBreakLines(tidyBreakSegments(segments, lastTime), points, tags, rates), ...retrace.segments],
    boxes: [...describeBreakBoxes(quietBoxes, timeZone), ...retrace.boxes],
    tags: tags.filter((t) => t.id.startsWith('breaks-ib')),
    retrace: retrace.layer,
  };
}
