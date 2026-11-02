import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import { formatClock, formatPrice, type SessionTag } from './alnGuide';

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
export function tidyHourSegments<T extends { endTime: number; label: string; showPrice: boolean; labelColor: string; compact?: boolean; touchText?: string; markerText?: string }>(
  segments: readonly T[],
  lastTime: number,
): T[] {
  return segments.map((s) => {
    if (s.endTime !== lastTime) return { ...s, label: '', showPrice: false, touchText: undefined, markerText: undefined };
    return { ...s, label: SHORT_LABELS[s.label] ?? s.label, labelColor: '#9aa4b2', compact: true };
  });
}
