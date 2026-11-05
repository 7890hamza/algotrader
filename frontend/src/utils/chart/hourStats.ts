import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import { formatClock, formatPrice, type SessionBox, type SessionTag } from './alnGuide';

/** ES 2016-2025 rates for one New York hour (see indicator-api HOUR_RATES). */
export interface HourRates {
  n: number;
  rev: number;
  /** "0" / "1" / "2" (minutes 0-19 / 20-39 / 40-59) -> [came back %, breaches]. */
  segs: Record<string, [number, number]>;
}

export function readHourStatsGuide(guide: JsonObject | undefined): Record<string, HourRates> | null {
  if (!guide || guide.kind !== 'hour_stats' || typeof guide.hours !== 'object' || guide.hours === null) return null;
  return guide.hours as unknown as Record<string, HourRates>;
}

const SEGMENT_WORDS = ['minutes 0-19', 'minutes 20-39', 'minutes 40-59'];
const UP_COLOR = '#3fb950';
const DOWN_COLOR = '#e0574a';
const GREY_BG = 'rgba(139, 148, 158, 0.22)';
const GREY_FG = '#c9d1d9';

const NEW_YORK_HOUR = new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'America/New_York' });

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const pts = (a: number, b: number): string => `${Math.abs(a - b).toFixed(2)} pts`;

/**
 * One chip per hour ("6 AM [H · 66%] ✓"), centered over the hour, with a plain recap on hover:
 * which prior-hour level broke and when, the odds for that hour and segment, MAE / MFE.
 */
export function buildHourTags(
  points: readonly IndicatorDataPoint[],
  hours: Record<string, HourRates>,
  timeZone: string,
): SessionTag[] {
  const sorted = [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)) && num(p, 'open') !== null)
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  const runs: IndicatorDataPoint[][] = [];
  for (const point of sorted) {
    const run = runs[runs.length - 1];
    const prev = run?.[run.length - 1];
    const sameHour =
      prev !== undefined &&
      num(prev, 'open') === num(point, 'open') &&
      num(prev, 'ph') === num(point, 'ph') &&
      Number(point.timestamp_ms) - Number(run[0].timestamp_ms) < 3_600_000;
    if (sameHour) run.push(point);
    else runs.push([point]);
  }
  const lastPoint = sorted[sorted.length - 1];
  const clock = (ms: number): string => formatClock(ms, timeZone);
  return runs.map((run) => {
    const first = run[0];
    const last = run[run.length - 1];
    const startMs = Number(first.timestamp_ms);
    const live = last === lastPoint;
    const open = num(first, 'open')!;
    const ph = num(first, 'ph');
    const pl = num(first, 'pl');
    const nyHour = Number(NEW_YORK_HOUR.format(new Date(startMs)));
    const rates = hours[String(nyHour)];
    const label = new Date(startMs).toLocaleTimeString('en-US', { hour: 'numeric', timeZone });
    const breach = run.find((p) => num(p, 'side') !== null);
    let top = Math.max(open, ph ?? open);
    // Zones are drawn for the current hour only, so only then does the chip sit above them.
    if (live) for (const p of run) for (const k of ['stretch_far', 'follow_far']) { const v = num(p, k); if (v !== null && v > top) top = v; }
    const tag: SessionTag = {
      separator: true,
      id: `hour@${startMs}`,
      startTime: Math.floor(startMs / 1000),
      endTime: Math.floor(Number(last.timestamp_ms) / 1000),
      top,
      date: label,
      pattern: 2,
      lines: [],
      result: 'none',
      chipBg: GREY_BG,
      chipFg: GREY_FG,
    };
    const all = rates ? `All ${label} hours: ${rates.rev.toFixed(1)}% of breaches came back to the open (${rates.n.toLocaleString()}).` : '';
    if (num(first, 'setup') !== 1) {
      tag.chipText = 'no setup';
      tag.lines = [`${label} hour: the open ${formatPrice(open)} was outside the prior hour's range, so no setup.`];
      return tag;
    }
    if (!breach) {
      tag.chipText = live ? 'waiting' : 'no break';
      tag.lines = [
        live
          ? `Waiting for a break of the prior hour high ${ph !== null ? formatPrice(ph) : ''} or low ${pl !== null ? formatPrice(pl) : ''}.`
          : 'Price stayed inside the prior hour range all hour.',
      ];
      if (all) tag.lines.push(all);
      return tag;
    }
    const side = num(breach, 'side')!;
    const seg = Math.max(0, Math.min(2, num(breach, 'seg') ?? 0));
    const rate = rates?.segs[String(seg)];
    const color = side > 0 ? UP_COLOR : DOWN_COLOR;
    const word = side > 0 ? 'high' : 'low';
    const level = side > 0 ? ph : pl;
    tag.chipText = `${side > 0 ? 'H' : 'L'}${rate ? ` · ${Math.round(rate[0])}%` : ''}`;
    tag.chipBg = rgba(color, 0.25);
    tag.chipFg = color;
    tag.lines = [
      `Broke the prior hour ${word}${level !== null ? ` ${formatPrice(level)}` : ''} at ${clock(Number(num(breach, 'breach_at')))} (${SEGMENT_WORDS[seg]})`,
      rate
        ? `Breaks in ${SEGMENT_WORDS[seg]} of this hour came back to the open ${rate[0].toFixed(1)}% (${rate[1].toLocaleString()} breaches)`
        : 'No past breaks to compare.',
    ];
    if (all) tag.lines.push(all);
    const sNear = num(breach, 'stretch_near');
    const sFar = num(breach, 'stretch_far');
    const fNear = num(breach, 'follow_near');
    const fFar = num(breach, 'follow_far');
    if (level !== null && sNear !== null && sFar !== null) {
      tag.lines.push(`MAE (past the ${word} first): half of hours ${formatPrice(sNear)} (${pts(sNear, level)}), 9 in 10 ${formatPrice(sFar)} (${pts(sFar, level)})`);
    }
    if (fNear !== null && fFar !== null) {
      tag.lines.push(`MFE (past the open after coming back): half ${formatPrice(fNear)} (${pts(fNear, open)}), 9 in 10 ${formatPrice(fFar)} (${pts(fFar, open)})`);
    }
    const revertMs = num(last, 'revert_at');
    if (revertMs !== null) {
      tag.result = 'reached';
      tag.lines.push(`Came back to the hour open ${formatPrice(open)} at ${clock(revertMs)}`);
    } else if (live) {
      tag.lines.push(`Watching for the return to the hour open ${formatPrice(open)}`);
    } else {
      tag.result = 'missed';
      tag.lines.push('Did not come back to the hour open');
    }
    return tag;
  });
}

/** Zones of the hour that is running now, once it has broken; past hours show theirs on hover. */
export function currentHourBoxes<T extends { endTime: number; compact?: boolean }>(boxes: readonly T[], lastTime: number): T[] {
  return boxes.filter((b) => b.endTime === lastTime).map((b) => ({ ...b, compact: true }));
}

const SHORT_LABELS: Record<string, string> = { 'Hour Open': 'Open', 'Prior H': 'Prior H', 'Prior L': 'Prior L' };

/**
 * Quiet lines: past hours keep their lines and markers but no text (the hour chip
 * shows the story on hover); the running hour gets small labels with prices.
 */
export function tidyHourSegments<T extends { id: string; endTime: number; label: string; showPrice: boolean; labelColor: string; compact?: boolean; touchText?: string; markerText?: string }>(
  segments: readonly T[],
  lastTime: number,
): T[] {
  // Past sessions also drop their zone mid-lines (P75): the zones are only drawn for the live one.
  return segments.filter((s) => s.endTime === lastTime || !/_mid@/.test(s.id)).map((s) => {
    if (s.endTime !== lastTime) return { ...s, label: '', showPrice: false, touchText: undefined, markerText: undefined };
    return { ...s, label: SHORT_LABELS[s.label] ?? s.label, labelColor: '#9aa4b2', compact: true };
  });
}

/** Share of prior-hour-high / -low breaks in each 20-minute slice, by New York hour. */
export type HourSlices = Record<string, { high: [number, number, number]; low: [number, number, number] }>;

export function readHourSlices(guide: JsonObject | undefined): HourSlices {
  return (guide && typeof guide.slices === 'object' && guide.slices !== null ? guide.slices : {}) as unknown as HourSlices;
}

const MAE_COLOR = '#14b8a6';
const MFE_COLOR = '#c026d3';
const BOX_COLOR = '#2e7d4f';
const FADED_GREY = 'rgba(138, 145, 156, 0.45)';
const FADED_GOLD = 'rgba(200, 150, 46, 0.45)';
const SLICE_WORDS = ['0–19', '20–39', '40–59'];
/** Bands run from the median toward the 75th percentile, this share of the way (thin, like NQ Stats). */
const BAND_SHARE = 0.45;

interface HourRun {
  points: IndicatorDataPoint[];
  start: number;
  end: number;
  open: number;
  ph: number | null;
  pl: number | null;
  setup: boolean;
  breach: IndicatorDataPoint | undefined;
  last: IndicatorDataPoint;
}

function hourRuns(points: readonly IndicatorDataPoint[]): HourRun[] {
  const sorted = [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)) && num(p, 'open') !== null)
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  const runs: IndicatorDataPoint[][] = [];
  for (const point of sorted) {
    const run = runs[runs.length - 1];
    const prev = run?.[run.length - 1];
    const same = prev !== undefined && num(prev, 'open') === num(point, 'open') && num(prev, 'ph') === num(point, 'ph')
      && Number(point.timestamp_ms) - Number(run[0].timestamp_ms) < 3_600_000;
    if (same) run.push(point);
    else runs.push([point]);
  }
  return runs.map((run) => ({
    points: run,
    start: Math.floor(Number(run[0].timestamp_ms) / 1000),
    end: Math.floor(Number(run[0].timestamp_ms) / 1000) + 3600,
    open: num(run[0], 'open')!,
    ph: num(run[0], 'ph'),
    pl: num(run[0], 'pl'),
    setup: num(run[0], 'setup') === 1,
    breach: run.find((p) => num(p, 'side') !== null),
    last: run[run.length - 1],
  }));
}

/** The fields of a session level segment this layout touches. */
export interface SessionLevelSegmentLike {
  id: string;
  startTime: number;
  endTime: number;
  label: string;
  color: string;
  showPrice: boolean;
  labelColor: string;
  compact?: boolean;
  touchText?: string;
  touchColor?: string;
  markerText?: string;
  markerColor?: string;
  sessionEndTime: number | null;
}

function barSecondsOf(points: readonly IndicatorDataPoint[]): number {
  let smallest = Number.POSITIVE_INFINITY;
  for (let i = 1; i < points.length; i += 1) {
    const d = (Number(points[i].timestamp_ms) - Number(points[i - 1].timestamp_ms)) / 1000;
    if (d > 0 && d < smallest) smallest = d;
  }
  return Number.isFinite(smallest) ? smallest : 60;
}

/**
 * NQ Stats-style Hour Stats: for the running hour, a dotted prior-high / prior-low box split in
 * three 20-minute slices with the break odds above / below each, the open labeled "XX% @ Open"
 * once a level is swept, and the MAE (teal, past the swept level) and MFE (magenta, past the open)
 * bands across the hour. Earlier hours keep faded lines and bands. Hovering an hour's box or bands
 * opens a play-by-play card.
 */
export function layoutHourStats<T extends SessionLevelSegmentLike>(
  points: readonly IndicatorDataPoint[],
  segments: readonly T[],
  hours: Record<string, HourRates>,
  slices: HourSlices,
  timeZone: string,
): { segments: T[]; boxes: SessionBox[] } {
  const runs = hourRuns(points);
  if (!runs.length) return { segments: [], boxes: [] };
  const bar = barSecondsOf(points);
  const current = runs[runs.length - 1];
  const clock = (ms: number): string => formatClock(ms, timeZone);
  const boxes: SessionBox[] = [];
  const cards = new Map<number, string[]>();
  for (const run of runs) {
    const live = run === current;
    const nyHour = Number(NEW_YORK_HOUR.format(new Date(run.start * 1000)));
    const rates = hours[String(nyHour)];
    const sl = slices[String(nyHour)];
    const label = new Date(run.start * 1000).toLocaleTimeString('en-US', { hour: 'numeric', timeZone });
    const lines = [`${label} hour · prior hour ${run.pl !== null ? formatPrice(run.pl) : '?'}–${run.ph !== null ? formatPrice(run.ph) : '?'} · open ${formatPrice(run.open)}`];
    const endT = run.end - bar;
    if (!run.setup) {
      lines.push("The hour opened outside the prior hour's range, so there's no setup this hour.");
    } else if (!run.breach) {
      if (live) {
        const minute = Math.floor((Math.floor(Number(run.last.timestamp_ms) / 1000) - run.start) / 60);
        const seg = Math.max(0, Math.min(2, Math.floor(minute / 20)));
        if (sl) lines.push(`Waiting for a break. In this hour, prior-high breaks came ${sl.high[0]}% / ${sl.high[1]}% / ${sl.high[2]}% in minutes 0–19 / 20–39 / 40–59 (prior low: ${sl.low[0]}% / ${sl.low[1]}% / ${sl.low[2]}%).`);
        const r = rates?.segs[String(seg)];
        if (r) lines.push(`A break now (minutes ${SLICE_WORDS[seg]}) came back to the open ${Math.round(r[0])}% of the time.`);
      } else {
        lines.push("Price stayed inside the prior hour's range all hour.");
      }
    } else {
      const side = num(run.breach, 'side')!;
      const seg = Math.max(0, Math.min(2, num(run.breach, 'seg') ?? 0));
      const r = rates?.segs[String(seg)];
      const lvl = side > 0 ? run.ph : run.pl;
      const word = side > 0 ? 'high' : 'low';
      lines.push(`1. ${clock(Number(num(run.breach, 'breach_at')))}: the prior hour ${word}${lvl !== null ? ` ${formatPrice(lvl)}` : ''} got swept (minutes ${SLICE_WORDS[seg]}).`);
      if (r) lines.push(`2. Breaks in that slice came back to the open ${Math.round(r[0])}% of the time (${r[1].toLocaleString()} breaks). So about ${10 - Math.round(r[0] / 10)} in 10 don't.`);
      const sN = num(run.breach, 'stretch_near');
      const sM = num(run.breach, 'stretch_mid');
      const fN = num(run.breach, 'follow_near');
      const fM = num(run.breach, 'follow_mid');
      if (sN !== null && sM !== null) {
        lines.push(`3. MAE (teal): before turning back, half of hours stretched to ${formatPrice(sN)} past the ${word}, 3 in 4 to ${formatPrice(sM)}. Well beyond that, the idea is likely wrong.`);
        const sB = sN + (sM - sN) * BAND_SHARE; // a thin band from the typical stretch toward the 3-in-4 one
        boxes.push({ id: `hs_mae@${run.start}`, startTime: run.start, endTime: endT, high: Math.max(sN, sB), low: Math.min(sN, sB), color: MAE_COLOR, label: '', noLabels: true, fillOpacity: live ? 0.3 : 0.08 });
      }
      if (fN !== null && fM !== null) {
        lines.push(`4. MFE (magenta): after getting back to the open, half of hours ran on to ${formatPrice(fN)}, 3 in 4 to ${formatPrice(fM)}. That's the next target.`);
        const fB = fN + (fM - fN) * BAND_SHARE;
        boxes.push({ id: `hs_mfe@${run.start}`, startTime: run.start, endTime: endT, high: Math.max(fN, fB), low: Math.min(fN, fB), color: MFE_COLOR, label: '', noLabels: true, fillOpacity: live ? 0.28 : 0.08 });
      }
      const back = num(run.last, 'revert_at');
      lines.push(back !== null ? `5. ${clock(back)}: back at the open ✓.` : live ? `5. Watching for the return to the open ${formatPrice(run.open)}.` : '5. It did not come back to the open.');
    }
    cards.set(run.start, lines);
    if (live && run.ph !== null && run.pl !== null) {
      boxes.push({
        id: `hs_box@${run.start}`, startTime: run.start, endTime: endT, high: run.ph, low: run.pl, color: BOX_COLOR, label: '',
        noLabels: true, fillOpacity: 0, dashed: true, hoverLines: lines,
        slices: sl ? { times: [run.start + 1200, run.start + 2400], top: sl.high.map((v) => `${Math.round(v)}%`), bottom: sl.low.map((v) => `${Math.round(v)}%`) } : undefined,
      });
    }
  }
  for (const b of boxes) if (!b.hoverLines) b.hoverLines = cards.get(b.startTime);
  const out = segments.map((s) => {
    const run = runs.find((r) => s.startTime >= r.start && s.startTime < r.end);
    const key = s.id.split('@')[0];
    if (!run) return s;
    if (run !== current) {
      return { ...s, label: '', showPrice: false, touchText: undefined, markerText: undefined, color: key === 'open' ? FADED_GOLD : FADED_GREY };
    }
    const side = run.breach ? num(run.breach, 'side') : null;
    const seg = run.breach ? Math.max(0, Math.min(2, num(run.breach, 'seg') ?? 0)) : null;
    const rates = hours[String(Number(NEW_YORK_HOUR.format(new Date(run.start * 1000))))];
    let text = s.label;
    if (key === 'open') {
      const r = seg !== null ? rates?.segs[String(seg)] : undefined;
      text = r ? `${Math.round(r[0])}% @ Open${num(run.last, 'revert_at') !== null ? ' ✓' : ''}` : 'Open';
    } else if (key === 'ph') text = side === 1 ? 'PHH Swept' : 'PHH';
    else if (key === 'pl') text = side === -1 ? 'PHL Swept' : 'PHL';
    return { ...s, label: text, showPrice: false, compact: true, labelColor: '#c9d1d9', touchText: undefined, markerText: undefined, sessionEndTime: run.end - bar };
  });
  return { segments: out, boxes };
}
