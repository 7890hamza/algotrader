import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint } from '@/types/contracts';
import { buildBreaksTags, inTen, mtfLayout, readBreaksGuide, tidyBreakSegments, type BreakRates } from '@/utils/chart/breaks';

const rates: BreakRates = {
  rth: {
    inside: { n: 1380, either: 82.4, one: 73.2, both: 9.2, upper: [75.0, 22.8], middle: [41.7, 37.7], lower: [19.3, 78.6] },
    gap_up: { n: 628, held: 88.4 },
    gap_down: { n: 356, held: 90.7 },
  },
  ib: { n: 2307, either: 98.1, above: [83.3, 43.9, 1247], below: [46.4, 81.8, 1045], ext: [0.62, 1.18] },
  eth: {
    inside: { n: 2164, either: 86.9, upper: [80.0, 20.5], middle: [48.0, 46.4], lower: [24.3, 76.2] },
    overnight: { other_held: 85.2, n_one: 1335, one_by_close: 64.2, n_none: 794 },
  },
};
const M = 60_000;
const OPEN = Date.UTC(2026, 9, 6, 13, 30); // Tue Oct 6, 9:30 New York = 6:30 Pacific
const TZ = 'America/Los_Angeles';

function day(extra: (i: number) => Record<string, number>, bars = 78): IndicatorDataPoint[] {
  return Array.from({ length: bars }, (_, i) => ({ timestamp_ms: OPEN + i * 5 * M, ...extra(i) }));
}

describe('Breaks chips', () => {
  it('reads the guide and rounds odds to "in 10"', () => {
    expect(readBreaksGuide({ kind: 'breaks', rates: rates as never })).not.toBeNull();
    expect(readBreaksGuide({ kind: 'hour_stats' })).toBeNull();
    expect(inTen(78.6)).toBe(8);
    expect(inTen(88.4)).toBe(9);
  });

  it('lower-third open: likely the pRTH low gets hit, ✓ once it does', () => {
    const points = day((i) => ({
      prth_h: 7850, prth_l: 7783, rth_setup: 0, rth_third: -1, rth_touch_h: 1, rth_touch_l: 1,
      ...(i >= 14 ? { rth_hit_l: OPEN + 14 * 5 * M } : {}),
    }), 40);
    const [tag] = buildBreaksTags(points, rates, TZ);
    expect(tag.chipText).toBe('Likely: pRTH low gets hit · 8 in 10');
    expect(tag.date).toBe('Tue');
    expect(tag.result).toBe('reached');
    expect(tag.lines[0]).toBe("Opened inside yesterday's RTH range, in the lower third");
    expect(tag.lines).toContain('So about 2 days in 10 it doesn\'t happen');
    expect(tag.lines).toContain('pRTH low hit at 7:40 AM');
  });

  it('gap up: the low stays untouched; settles only at the close', () => {
    const live = day(() => ({ prth_h: 7850, prth_l: 7783, rth_setup: 1, rth_touch_h: 0, rth_touch_l: 1 }), 40);
    expect(buildBreaksTags(live, rates, TZ)[0]).toMatchObject({ chipText: 'Likely: pRTH low stays untouched · 9 in 10', result: 'none' });
    const full = day(() => ({ prth_h: 7850, prth_l: 7783, rth_setup: 1, rth_touch_h: 0, rth_touch_l: 1 }));
    expect(buildBreaksTags(full, rates, TZ)[0].result).toBe('reached');
    const broke = day((i) => ({ prth_h: 7850, prth_l: 7783, rth_setup: 1, ...(i > 50 ? { rth_hit_l: OPEN } : {}) }), 60);
    expect(buildBreaksTags(broke, rates, TZ)[0].result).toBe('missed');
  });

  it('middle third has no favorite; finished without a hit is ✕', () => {
    const points = day(() => ({ prth_h: 7850, prth_l: 7783, rth_setup: 0, rth_third: 0 }));
    const [tag] = buildBreaksTags(points, rates, TZ);
    expect(tag.chipText).toBe('One side usually gets hit · 8 in 10');
    expect(tag.result).toBe('missed');
    expect(tag.lines).toContain('Neither line was hit by the close');
  });

  it('IB chip: forming, then the favored side', () => {
    const forming = day(() => ({ ib_box_h: 7844, ib_box_l: 7826 }), 6);
    expect(buildBreaksTags(forming, rates, TZ)[0]).toMatchObject({ date: 'IB', chipText: 'forming' });
    const points = day((i): Record<string, number> => (i < 12
      ? { ib_box_h: 7844, ib_box_l: 7826.75 }
      : { ib_h: 7844, ib_l: 7826.75, ib_mid: 7835.38, ib_side: 1, ib_valid: 1, ...(i >= 16 ? { ib_hit_h: OPEN + 16 * 5 * M, ib_ext_med: 7854.69, ib_ext_p75: 7864.35 } : {}) }), 30);
    const [tag] = buildBreaksTags(points, rates, TZ);
    expect(tag.chipText).toBe('Likely: IB high gets hit · 8 in 10');
    expect(tag.result).toBe('reached');
    expect(tag.endTime).toBe(Math.floor((OPEN + 11 * 5 * M) / 1000)); // centered over the IB box
    expect(tag.lines.at(-1)).toBe('After the break, half of days reach 7,854.69, 1 in 4 reach 7,864.35');
  });

  it('quiets past sessions and keeps small labels on the latest one, even after it closed', () => {
    const seg = { id: 'prth_h@0', startTime: 0, endTime: 10, label: 'pRTH High', showPrice: true, labelColor: '#fff', touchText: 'Hit' };
    const [past, live] = tidyBreakSegments([seg, { ...seg, id: 'prth_h@15', startTime: 15, endTime: 20 }], 99);
    expect(past).toMatchObject({ label: '', showPrice: false, touchText: undefined });
    expect(live).toMatchObject({ label: 'pRTH High', compact: true });
  });

  it('MTF layout: only running lines, weekly as a short stub', () => {
    const seg = (id: string, start: number, end: number) => ({ id, startTime: start, endTime: end, label: id, showPrice: false });
    const out = mtfLayout([seg('d_open@1', 100, 9000), seg('d_open@0', 0, 50), seg('w_+1@0', 0, 9000)], 9000, { pastDays: false, stubSeconds: 3600 });
    expect(out.map((s) => s.id)).toEqual(['d_open@1', 'w_+1@0']);
    expect(out[1].startTime).toBe(5400);
    expect(mtfLayout([seg('d_open@0', 0, 50)], 9000, { pastDays: true, stubSeconds: 3600 })[0].label).toBe('');
  });
});
