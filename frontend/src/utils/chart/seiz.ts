import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

import type { SessionBox } from './alnGuide';

/**
 * SEIZ: shaded percentile bands per candle of the chosen zone timeframe.
 *
 * Every zone (internal / external high / low) is four stacked bands from its reference
 * (the open for internal zones, the last high / low for external ones) out to the 50th, 75th,
 * 85th and 99th percentile; the deeper the colour, the rarer the move. Each band is labelled at
 * its outer edge. Zones start where they switch on (the candle open, or the bar that broke the
 * last high / low) and run to the end of the candle, or to the bar where they switched off.
 */

export interface SeizBand { pct: number; label: string; alpha: number; odds: string }
export interface SeizZone { name: string; where: string; color: string }
export interface SeizGuide {
  zones: Record<'ih' | 'il' | 'eh' | 'el', SeizZone>;
  bands: SeizBand[];
  stat: { color: string; text: string };
  timeframes: { key: string; label: string }[];
  source: string;
}

export function readSeizGuide(guide: JsonObject | undefined): SeizGuide | null {
  if (!guide || guide.kind !== 'seiz' || !Array.isArray(guide.bands) || typeof guide.zones !== 'object') return null;
  return guide as unknown as SeizGuide;
}

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const ZONES = ['eh', 'ih', 'il', 'el'] as const;
const OPEN_RULE_COLOR = '#8a919c';

function fmt(price: number): string {
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Run { from: number; to: number }

/** Contiguous stretches of rows where `key` has a value (and the candle stays the same). */
function runsOf(rows: IndicatorDataPoint[], key: string): Run[] {
  const runs: Run[] = [];
  let start = -1;
  for (let i = 0; i <= rows.length; i++) {
    const on = i < rows.length && num(rows[i], key) !== null;
    if (on && start < 0) start = i;
    if (!on && start >= 0) {
      runs.push({ from: start, to: i - 1 });
      start = -1;
    }
  }
  return runs;
}

export function layoutSeiz(
  points: readonly IndicatorDataPoint[],
  guide: SeizGuide,
  options: { zoneLabel: string; barSeconds: number },
): SessionBox[] {
  const sorted = [...points]
    .filter((p) => Number.isFinite(Number(p.timestamp_ms)) && num(p, 'start') !== null)
    .sort((a, b) => Number(a.timestamp_ms) - Number(b.timestamp_ms));
  // group rows by candle (same start time)
  const candles: IndicatorDataPoint[][] = [];
  for (const p of sorted) {
    const last = candles[candles.length - 1];
    if (last && num(last[0], 'start') === num(p, 'start')) last.push(p);
    else candles.push([p]);
  }
  const boxes: SessionBox[] = [];
  const sec = (p: IndicatorDataPoint): number => Math.floor(Number(p.timestamp_ms) / 1000);
  candles.forEach((rows, ci) => {
    const first = rows[0];
    const last = rows[rows.length - 1];
    const candleEnd = Math.floor((num(first, 'end') ?? Number(last.timestamp_ms)) / 1000) - options.barSeconds;
    const isLast = ci === candles.length - 1;
    const open = num(first, 'open');
    const startT = sec(first);
    if (open !== null) {
      boxes.push({
        id: `seiz-rule-${startT}`, startTime: startT, endTime: startT, high: open, low: open,
        color: OPEN_RULE_COLOR, label: '', fillOpacity: 0, noLabels: true, rule: true,
      });
    }
    for (const z of ZONES) {
      const zone = guide.zones[z];
      const high = z === 'eh' || z === 'ih';
      for (const run of runsOf(rows, `${z}50`)) {
        const a = rows[run.from];
        const b = rows[run.to];
        // a zone still on at the candle's last bar runs to the end of the candle
        const reachesEnd = run.to === rows.length - 1;
        const endT = reachesEnd ? (isLast ? Math.max(candleEnd, sec(b)) : sec(b)) : sec(b);
        const ref = z === 'eh' ? num(a, 'ph') : z === 'el' ? num(a, 'pl') : num(a, 'open');
        if (ref === null) continue;
        let inner = ref;
        guide.bands.forEach((band, bi) => {
          const outer = num(a, `${z}${band.pct}`);
          if (outer === null) return;
          const top = high ? outer : inner;
          const bottom = high ? inner : outer;
          if (top - bottom > 1e-9) {
            boxes.push({
              id: `seiz-${z}${band.pct}-${sec(a)}`,
              startTime: sec(a),
              endTime: endT,
              high: top,
              low: bottom,
              color: zone.color,
              label: '',
              fillOpacity: band.alpha,
              noLabels: true,
              edgeLabel: band.label,
              edgeAt: high ? 'top' : 'bottom',
              hoverLines: [
                `${options.zoneLabel} · ${zone.name} · ${band.label.replace(' ✕', '')}`,
                `${zone.where}. Of past candles that made the same move, ${band.odds}.`,
                `${band.label.replace(' ✕', '')} at ${fmt(outer)}${bi === 3 ? ' (the ✕ marks the edge of normal)' : ''}`,
              ],
            });
          }
          inner = outer;
        });
      }
    }
    // Stat Zone: one box per side, dashed at the median
    for (const side of ['h', 'l'] as const) {
      const hiKey = side === 'h' ? 'st_h_hi' : 'st_l_hi';
      const loKey = side === 'h' ? 'st_h_lo' : 'st_l_lo';
      const top = num(first, hiKey);
      const bottom = num(first, loKey);
      const mid = num(first, side === 'h' ? 'st_h_mid' : 'st_l_mid');
      if (top === null || bottom === null) continue;
      boxes.push({
        id: `seiz-stat-${side}-${startT}`,
        startTime: startT,
        endTime: isLast ? Math.max(candleEnd, sec(last)) : sec(last),
        high: Math.max(top, bottom),
        low: Math.min(top, bottom),
        color: guide.stat.color,
        label: '',
        fillOpacity: 0.16,
        noLabels: true,
        outline: true,
        ...(mid !== null ? { midline: mid } : {}),
        hoverLines: [
          `${options.zoneLabel} · Stat Zone (${side === 'h' ? 'high' : 'low'})`,
          'Where this timeframe typically gets to: the middle half of past candles, dashed at the median.',
        ],
      });
    }
  });
  return boxes;
}

/** Dashboard cell text: "85 Ext", "50 Int", "<50 Ext", "–". */
export function dashCell(code: number | null): string {
  if (code === null) return '';
  if (code >= 100) return code === 100 ? '<50 Ext' : `${code - 100} Ext`;
  return code === 0 ? '–' : `${code} Int`;
}

/** One timeframe of the candle strip: band codes and the candle in the last candle's range. */
export interface SeizStripCell {
  key: string;
  label: string;
  hi: number | null;
  lo: number | null;
  pg: number | null;
  o: number | null;
  h: number | null;
  l: number | null;
  c: number | null;
}

const SHORT_TFS = ['15m', '30m', '1h', '2h'];

/** Brightness of a wick that broke out: rarer bands are brighter. */
export function seizShade(code: number | null): number {
  const p = code === null ? 0 : code % 100;
  return p >= 99 ? 1 : p >= 85 ? 0.9 : p >= 75 ? 0.65 : p >= 50 ? 0.55 : 0.45;
}

/**
 * The one sentence under the strip: short timeframes stretched to the 85th+ outside their last
 * candle on one side, and what the daily is doing on that side. Null when nothing lines up.
 */
export function seizPairing(cells: readonly SeizStripCell[]): string | null {
  for (const side of ['lo', 'hi'] as const) {
    const hot = cells.filter((c) => SHORT_TFS.includes(c.key) && (c[side] ?? 0) >= 185);
    if (!hot.length) continue;
    const best = Math.max(...hot.map((c) => (c[side] ?? 0) - 100));
    const names = hot.map((c) => c.label);
    const list = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0];
    const where = side === 'lo' ? 'below their last lows' : 'above their last highs';
    const day = cells.find((c) => c.key === '1d');
    const code = day?.[side] ?? 0;
    const daily = code >= 100
      ? `the daily broke its last ${side === 'lo' ? 'low' : 'high'} too`
      : `the daily is only a normal ${side === 'lo' ? 'dip' : 'push'}`;
    return `${list} stretched to the ${best}th ${where}, while ${daily}`;
  }
  return null;
}
