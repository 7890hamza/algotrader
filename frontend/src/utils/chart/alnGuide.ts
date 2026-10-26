import type { IndicatorDataPoint, IndicatorOutputMetadata, JsonObject } from '@/types/contracts';

import type { SessionLevelSegment } from './sessionLevels';

/** One drawn session box: Asia, London or New York. */
export interface SessionBox {
  id: string;
  /** Epoch seconds of the first and last bar inside the box. */
  startTime: number;
  endTime: number;
  high: number;
  low: number;
  color: string;
  label: string;
}

export interface AlnPatternStats {
  n: number;
  high: number;
  low: number;
  high_first: number;
  low_after_high_first: number;
  high_after_low_first: number;
  neither: number;
}

export interface AlnGuideConfig {
  stats: Record<string, AlnPatternStats>;
  watchColor: string;
  otherColor: string;
}

export type GuideTone = 'live' | 'done' | 'changed' | 'waiting';

export interface GuideStep {
  key: 'asia' | 'london' | 'lock' | 'watch' | 'done';
  label: string;
  state: 'done' | 'current' | 'todo';
}

export interface GuideCheck {
  question: string;
  answer: string;
  state: 'yes' | 'no' | 'open';
}

export interface GuideRecentDay {
  ago: number;
  kind: 'hit' | 'miss' | 'flat';
  text: string;
}

export interface GuideView {
  phase: 'asia' | 'london' | 'newyork' | 'over' | 'none';
  /** Overnight pattern 1-4: a guess while London is still trading, final from 5:00 AM. */
  pattern: number | null;
  patternFinal: boolean;
  sentence: string;
  tone: GuideTone;
  steps: GuideStep[];
  checks: GuideCheck[];
  recent: GuideRecentDay[];
  details: { label: string; value: string }[];
}

const NY_SESSION_SECONDS = 8 * 3600;
const MAX_GAP_BARS = 5;
const NEAR_POINTS = 3;
const CLOSE_TARGET_POINTS = 2;

const num = (point: IndicatorDataPoint | null | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

export function formatPrice(price: number): string {
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatClock(epochMs: number, timeZone: string): string {
  return new Date(epochMs).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone });
}

/** 74 -> "about 3 out of 4 days" */
export function inWords(pct: number): string {
  const options: [number, string][] = [
    [1 / 2, '1 out of 2'], [3 / 5, '3 out of 5'], [2 / 3, '2 out of 3'], [7 / 10, '7 out of 10'],
    [3 / 4, '3 out of 4'], [4 / 5, '4 out of 5'], [9 / 10, '9 out of 10'],
  ];
  let best = options[0];
  for (const option of options) {
    if (Math.abs(option[0] - pct / 100) < Math.abs(best[0] - pct / 100)) best = option;
  }
  return `about ${best[1]} days`;
}

export function readGuideConfig(guide: JsonObject | undefined): AlnGuideConfig | null {
  if (!guide || guide.kind !== 'aln' || typeof guide.stats !== 'object' || guide.stats === null) return null;
  const colors = (guide.colors ?? {}) as JsonObject;
  return {
    stats: guide.stats as unknown as Record<string, AlnPatternStats>,
    watchColor: typeof colors.watch === 'string' ? colors.watch : '#e9c46a',
    otherColor: typeof colors.other === 'string' ? colors.other : '#56606b',
  };
}

function sortedPoints(points: readonly IndicatorDataPoint[]): IndicatorDataPoint[] {
  return [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)))
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
}

function barSeconds(points: readonly IndicatorDataPoint[]): number {
  let smallest = Number.POSITIVE_INFINITY;
  for (let i = 1; i < points.length; i += 1) {
    const diff = (Number(points[i].timestamp_ms) - Number(points[i - 1].timestamp_ms)) / 1000;
    if (diff > 0 && diff < smallest) smallest = diff;
  }
  return Number.isFinite(smallest) ? smallest : 60;
}

/** Boxes from the running session ranges (outputs of type "box"). */
export function buildSessionBoxes(
  points: readonly IndicatorDataPoint[],
  outputs: Record<string, IndicatorOutputMetadata>,
): SessionBox[] {
  const sorted = sortedPoints(points);
  const maxGap = barSeconds(sorted) * MAX_GAP_BARS;
  const groups = new Map<string, { high?: string; low?: string; color: string; label: string }>();
  for (const [key, output] of Object.entries(outputs)) {
    if (output.type !== 'box' || typeof output.box !== 'string') continue;
    const group = groups.get(output.box) ?? {
      color: typeof output.plotOptions?.color === 'string' ? output.plotOptions.color : '#9aa4b2',
      label: typeof output.label === 'string' ? output.label : output.box,
    };
    if (output.edge === 'high') group.high = key;
    if (output.edge === 'low') group.low = key;
    groups.set(output.box, group);
  }

  const boxes: SessionBox[] = [];
  for (const [name, group] of groups) {
    if (!group.high || !group.low) continue;
    let current: SessionBox | null = null;
    for (const point of sorted) {
      const high = num(point, group.high);
      const low = num(point, group.low);
      const time = Math.floor(Number(point.timestamp_ms) / 1000);
      if (high === null || low === null) {
        if (current) boxes.push(current);
        current = null;
        continue;
      }
      // Running ranges only widen inside one session; a narrower range or a long gap starts a new box.
      if (current && time - current.endTime <= maxGap && high >= current.high && low <= current.low) {
        current.endTime = time;
        current.high = high;
        current.low = low;
        continue;
      }
      if (current) boxes.push(current);
      current = { id: `${name}@${time}`, startTime: time, endTime: time, high, low, color: group.color, label: group.label };
    }
    if (current) boxes.push(current);
  }
  return boxes;
}

/** London's high and low carried through each New York session: one "watch" line, one "changes the story" line. */
export function buildAlnGuideLines(
  points: readonly IndicatorDataPoint[],
  config: AlnGuideConfig,
): SessionLevelSegment[] {
  const sorted = sortedPoints(points);
  const bar = barSeconds(sorted);
  const maxGap = bar * MAX_GAP_BARS;
  const segments: SessionLevelSegment[] = [];
  for (const side of ['high', 'low'] as const) {
    let current: SessionLevelSegment | null = null;
    let lastPoint: IndicatorDataPoint | null = null;
    const finish = (): void => {
      if (current && lastPoint) {
        const pattern = num(lastPoint, 'pattern');
        const watchSide = pattern === 3 ? 'high' : pattern === 4 ? 'low' : null;
        const isWatch = watchSide === side;
        const reached = num(lastPoint, side === 'high' ? 'up_at' : 'dn_at') !== null;
        const name = side === 'high' ? 'London high' : 'London low';
        current.label = watchSide === null ? name : isWatch ? `${reached ? 'Reached' : 'Watch'} · ${name}` : `Changes the story · ${name}`;
        current.color = isWatch ? config.watchColor : config.otherColor;
        current.labelColor = isWatch ? config.watchColor : config.otherColor;
        current.lineWidth = isWatch ? 2 : 1;
        current.lineStyle = isWatch ? 0 : 2;
        segments.push(current);
      }
      current = null;
    };
    for (const point of sorted) {
      const price = num(point, side === 'high' ? 'ref_london_high' : 'ref_london_low');
      const time = Math.floor(Number(point.timestamp_ms) / 1000);
      if (price === null) {
        finish();
        continue;
      }
      if (current && current.price === price && time - current.endTime <= maxGap) {
        current.endTime = time;
        lastPoint = point;
        continue;
      }
      finish();
      lastPoint = point;
      current = {
        id: `aln-${side}@${time}`,
        startTime: time,
        endTime: time,
        price,
        label: '',
        color: config.otherColor,
        lineWidth: 1,
        lineStyle: 2,
        touch: null,
        labelColor: config.otherColor,
        showPrice: false,
        sessionEndTime: time + NY_SESSION_SECONDS - bar,
      };
    }
    finish();
  }
  return segments;
}

const PATTERN_TEXT: Record<number, string> = {
  1: 'London broke both sides of Asia',
  2: 'London stayed inside Asia\'s range',
  3: 'London broke Asia\'s high only',
  4: 'London broke Asia\'s low only',
};

function recentText(code: number, ago: number): GuideRecentDay {
  const pattern = Math.floor(code / 100);
  const reached = Math.floor(code / 10) % 10 === 1;
  const otherFirst = code % 10 === 1;
  const when = ago === 1 ? 'Last session' : `${ago} sessions ago`;
  if (pattern === 1 || pattern === 2) {
    return { ago, kind: 'flat', text: `${when}: ${PATTERN_TEXT[pattern]}. No clear lean.` };
  }
  const level = pattern === 3 ? 'London\'s high' : 'London\'s low';
  const outcome = reached
    ? `New York reached ${level}${otherFirst ? ', after going to the other side first' : ''}.`
    : `${level} was never reached.`;
  return { ago, kind: reached ? 'hit' : 'miss', text: `${when}: ${PATTERN_TEXT[pattern] ?? 'Unknown pattern'}. ${outcome}` };
}

function steps(current: GuideStep['key']): GuideStep[] {
  const order: [GuideStep['key'], string][] = [
    ['asia', 'Asia'], ['london', 'London'], ['lock', '5:00 AM'], ['watch', 'Watch'], ['done', 'Done'],
  ];
  const at = order.findIndex(([key]) => key === current);
  return order.map(([key, label], i) => ({ key, label, state: i < at ? 'done' : i === at ? 'current' : 'todo' }));
}

/**
 * The walk-through for the latest session in `points`: what happened, what usually
 * happens next, and what would change that. It never says buy or sell.
 */
export function buildGuideView(
  points: readonly IndicatorDataPoint[],
  config: AlnGuideConfig,
  timeZone: string,
): GuideView {
  const sorted = sortedPoints(points);
  const latest = sorted[sorted.length - 1] ?? null;
  const empty: GuideView = { phase: 'none', pattern: null, patternFinal: false, sentence: 'Waiting for data.', tone: 'waiting', steps: steps('asia'), checks: [], recent: [], details: [] };
  if (!latest) return empty;

  const clock = (ms: number): string => formatClock(ms, timeZone);
  const lastNy = [...sorted].reverse().find((p) => num(p, 'pattern') !== null) ?? null;
  const phase: GuideView['phase'] = num(latest, 'pattern') !== null
    ? 'newyork'
    : num(latest, 'london_high') !== null
      ? 'london'
      : num(latest, 'asia_high') !== null
        ? 'asia'
        : lastNy ? 'over' : 'none';

  if (phase === 'asia') {
    const h = num(latest, 'asia_high')!;
    const l = num(latest, 'asia_low')!;
    return { ...empty, phase, tone: 'waiting', steps: steps('asia'),
      sentence: `Asia is setting tonight's range: ${formatPrice(l)} to ${formatPrice(h)}.`,
      checks: [{ question: 'Wait for 5:00 AM', answer: 'Nothing to watch until London finishes.', state: 'open' }] };
  }
  if (phase === 'london') {
    const asia = [...sorted].reverse().find((p) => num(p, 'asia_high') !== null);
    const ah = num(asia, 'asia_high');
    const al = num(asia, 'asia_low');
    const lh = num(latest, 'london_high')!;
    const ll = num(latest, 'london_low')!;
    let what = 'London is staying inside Asia\'s range so far.';
    let soFar: number | null = null;
    if (ah !== null && al !== null) {
      const up = lh > ah;
      const dn = ll < al;
      soFar = up && dn ? 1 : up ? 3 : dn ? 4 : 2;
      what = up && dn ? 'London is pushing above Asia\'s high and below its low.'
        : up ? 'London is pushing above Asia\'s high.'
          : dn ? 'London is pushing below Asia\'s low.' : what;
    }
    return { ...empty, phase, pattern: soFar, tone: 'waiting', steps: steps('london'),
      sentence: `${what} The picture locks at 5:00 AM.`,
      checks: [{ question: 'Wait for 5:00 AM', answer: 'The pattern isn\'t set until London closes.', state: 'open' }] };
  }

  const p = lastNy!;
  const pattern = num(p, 'pattern')!;
  const s = config.stats[`P${pattern}`];
  const lh = num(p, 'ref_london_high')!;
  const ll = num(p, 'ref_london_low')!;
  const upAt = num(p, 'up_at');
  const dnAt = num(p, 'dn_at');
  const recent: GuideRecentDay[] = [];
  for (let k = 1; k <= 8; k += 1) {
    const code = num(p, `recent_${k}`);
    if (code !== null) recent.push(recentText(code, k));
  }
  const details = s ? [
    { label: 'Pattern', value: `P${pattern}` },
    { label: 'Takes London high', value: `${s.high}%` },
    { label: 'Takes London low', value: `${s.low}%` },
    { label: 'High goes first', value: `${s.high_first}%` },
    { label: 'Past sessions like this', value: s.n.toLocaleString() },
  ] : [];
  const sdevPts = num(p, 'sdev_pts');
  if (sdevPts !== null) details.push({ label: '1 SDEV', value: `${sdevPts.toFixed(2)} pts` });
  const over = phase === 'over';

  if (pattern === 1 || pattern === 2) {
    const first = upAt !== null && (dnAt === null || upAt <= dnAt) ? ['high', upAt] as const
      : dnAt !== null ? ['low', dnAt] as const : null;
    return {
      phase, pattern, patternFinal: true, recent, details, steps: steps(over ? 'done' : 'watch'), tone: 'live',
      sentence: pattern === 1
        ? 'London broke both sides of Asia. Today has no clear lean: it\'s close to a coin flip.'
        : 'London stayed inside Asia\'s range. New York usually breaks out of London\'s range, often on both sides.',
      checks: [
        { question: 'No clear lean today', answer: PATTERN_TEXT[pattern] + '.', state: 'open' },
        { question: 'Which London level goes first?', answer: first ? `London's ${first[0]}, at ${clock(first[1])}.` : 'Neither yet.', state: first ? 'yes' : 'open' },
      ],
    };
  }

  const watch = pattern === 3 ? 'high' : 'low';
  const other = pattern === 3 ? 'low' : 'high';
  const watchPrice = pattern === 3 ? lh : ll;
  const wAt = pattern === 3 ? upAt : dnAt;
  const oAt = pattern === 3 ? dnAt : upAt;
  const pct = s ? (pattern === 3 ? s.high : s.low) : null;
  const otherFirst = oAt !== null && (wAt === null || oAt < wAt);

  let sentence: string;
  let tone: GuideTone = 'live';
  let step: GuideStep['key'] = 'watch';
  if (wAt !== null && !otherFirst) {
    sentence = `Done: London's ${watch} was reached at ${clock(wAt)}.`;
    tone = 'done';
    step = 'done';
  } else if (wAt !== null && otherFirst) {
    sentence = `London's ${other} broke first at ${clock(oAt!)}, and London's ${watch} was still reached later, at ${clock(wAt)}.`;
    tone = 'done';
    step = 'done';
  } else if (otherFirst) {
    sentence = `London's ${other} broke first, at ${clock(oAt!)}. Today's lean is gone: it's closer to a coin flip now.`;
    tone = 'changed';
  } else if (over) {
    sentence = `New York closed without reaching London's ${watch}. That happens on about 1 in 4 or 5 days like this.`;
    tone = 'changed';
    step = 'done';
  } else {
    sentence = `${PATTERN_TEXT[pattern]}. On days like this, New York usually reaches London's ${watch} (${formatPrice(watchPrice)})${pct !== null ? `, ${inWords(pct)}` : ''}.`;
  }

  const checks: GuideCheck[] = [];
  checks.push({
    question: `Did London's ${other} break first?`,
    answer: otherFirst ? `Yes, at ${clock(oAt!)}. The story changed.` : wAt !== null ? 'No. The watch level came first.' : 'Not so far.',
    state: otherFirst ? 'no' : wAt !== null ? 'yes' : 'open',
  });
  const open = num(p, 'ny_open');
  if (open !== null) {
    const dist = Math.abs(watchPrice - open);
    checks.push({
      question: 'Is the watch level far enough away?',
      answer: dist < CLOSE_TARGET_POINTS
        ? `No: only ${dist.toFixed(2)} pts from the 5:00 open. Nothing left to aim for.`
        : `Yes: ${dist.toFixed(2)} pts from the 5:00 open.`,
      state: dist < CLOSE_TARGET_POINTS ? 'no' : 'yes',
    });
    if (sdevPts !== null) {
      let near: [string, number] | null = null;
      for (const m of [0.5, 1, 1.5]) {
        for (const sign of [1, -1]) {
          const gap = Math.abs(open + sign * m * sdevPts - watchPrice);
          if (gap <= NEAR_POINTS && (!near || gap < near[1])) near = [`${sign > 0 ? '+' : '-'}${m}`, gap];
        }
      }
      checks.push({
        question: 'Is an SDEV line near it?',
        answer: near ? `Yes: the ${near[0]} line is ${near[1].toFixed(2)} pts away. Two levels agree.` : 'No SDEV line close to it.',
        state: near ? 'yes' : 'open',
      });
    }
  }
  return { phase, pattern, patternFinal: true, sentence, tone, steps: steps(step), checks, recent, details };
}
