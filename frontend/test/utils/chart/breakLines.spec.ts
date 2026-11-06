import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint } from '@/types/contracts';
import { annotateBreakLines, layoutBreaks } from '@/utils/chart/breakLines';
import type { BreakRates } from '@/utils/chart/breaks';
import { buildRetrace } from '@/utils/chart/retrace';
import type { SessionLevelSegment } from '@/utils/chart/sessionLevels';

const rates: BreakRates = {
  rth: { inside: { n: 1380, either: 82.4, one: 73.2, both: 9.2, upper: [75, 22.8], middle: [41.7, 37.7], lower: [19.3, 78.6] }, gap_up: { n: 628, held: 88.4 }, gap_down: { n: 356, held: 90.7 } },
  ib: { n: 2307, either: 98.1, above: [83.3, 43.9, 1247], below: [46.4, 81.8, 1045], ext: [0.62, 1.18] },
  eth: { inside: { n: 2164, either: 86.9, upper: [80, 20.5], middle: [48, 46.4], lower: [24.3, 76.2] }, overnight: { other_held: 85.2, n_one: 1335, one_by_close: 64.2, n_none: 794 } },
};
const M = 60_000;
const OPEN = Date.UTC(2026, 9, 6, 13, 30); // 9:30 New York
const seg = (id: string, start: number, end: number, price: number): SessionLevelSegment => ({
  id, startTime: start, endTime: end, price, label: id, color: '#888', lineWidth: 1, lineStyle: 0, touch: null, labelColor: '#fff', showPrice: true, sessionEndTime: null,
});

describe('Breaks lines', () => {
  it('writes the odds on the running pRTH lines and adds hover text', () => {
    const points: IndicatorDataPoint[] = Array.from({ length: 20 }, (_, i) => ({
      timestamp_ms: OPEN + i * 5 * M, prth_h: 7850, prth_l: 7783, rth_setup: 0, rth_third: -1, ...(i >= 10 ? { rth_hit_l: OPEN + 50 * M } : {}),
    }));
    const s0 = OPEN / 1000;
    const s1 = (OPEN + 95 * M) / 1000;
    const [h, l] = annotateBreakLines([seg(`prth_h@${s0}`, s0, s1, 7850), seg(`prth_l@${s0}`, s0, s1, 7783)], points,
      [{ id: `breaks-rth@${OPEN}`, startTime: s0, endTime: s1, top: 7850, date: 'Tue', pattern: 2, lines: ['story'], result: 'none' }], rates);
    expect(h.note).toBe('19% to get hit');
    expect(l.note).toBe('79% to get hit ✓');
    expect(l.hoverLines).toEqual(['story']);
  });

  it('pETH after 6:30 AM: high hit overnight -> the low likely holds', () => {
    const start = OPEN - 15.5 * 3_600_000; // 18:00 New York the day before
    const points: IndicatorDataPoint[] = [
      { timestamp_ms: start, peth_h: 7860, peth_l: 7790, eth_setup: 0, eth_third: 0 },
      { timestamp_ms: start + 3_600_000, peth_h: 7860, peth_l: 7790, eth_setup: 0, eth_third: 0, eth_hit_h: start + 3_600_000 },
      { timestamp_ms: OPEN, peth_h: 7860, peth_l: 7790, eth_setup: 0, eth_third: 0, eth_hit_h: start + 3_600_000 },
    ];
    const a = start / 1000;
    const b = OPEN / 1000;
    const [h, l] = annotateBreakLines([seg(`peth_h@${a}`, a, b, 7860), seg(`peth_l@${a}`, a, b, 7790)], points, [], rates);
    expect(h.note).toBe('Hit overnight');
    expect(l.note).toBe('85% holds');
    expect(l.hoverLines?.[0]).toContain('Overnight already hit the pETH high');
  });
});

describe('Breaks retracement layer', () => {
  it('builds zones, the live 40 / 60 / 100% lines, legs and In / Out marks', () => {
    const base = { rt_dir: 1, rt_start: 100, rt_end: 120, rt_start_at: OPEN, rt_end_at: OPEN + 10 * M };
    const points: IndicatorDataPoint[] = [
      { timestamp_ms: OPEN + 10 * M, rt_zone: 0, ...base },
      { timestamp_ms: OPEN + 20 * M, rt_zone: 0, ...base, rt_in_at: OPEN + 15 * M, rt_in_px: 112, rt_out_at: OPEN + 20 * M, rt_out_px: 112.5, rt_res: 1 },
      { timestamp_ms: OPEN + 30 * M, rt_zone: 1, rt_dir: 1, rt_start: 110, rt_end: 125, rt_start_at: OPEN + 15 * M, rt_end_at: OPEN + 30 * M },
    ];
    const r = buildRetrace(points, { kind: 'breaks', retrace: { zone: [0.4, 0.6], up: '#0f0', down: '#f00', leg: '#ff0' } }, 'America/Los_Angeles');
    expect(r.boxes[0]).toMatchObject({ high: 120, low: 100, fillOpacity: 0.07 }); // the whole leg (grey)
    expect(r.boxes[1]).toMatchObject({ high: 112, low: 108, fillOpacity: 0.2 }); // its 40-60% band
    expect(r.boxes[0].hoverLines?.[0]).toContain('IB leg');
    expect(r.boxes[1].hoverLines?.[2]).toContain('In: reached the zone');
    expect(r.boxes[1].hoverLines?.[3]).toContain('made a new high ✓');
    expect(r.segments.filter((s) => /^rt_(40|60)@/.test(s.id)).map((s) => s.label)).toEqual(['40%', '60%']);
    expect(r.layer?.legs.map((p) => p.price)).toEqual([100, 120, 110, 125]);
    expect(r.layer?.marks[0]).toMatchObject({ text: 'In', price: 112, dot: true, below: true });
    expect(r.layer?.marks[1]).toMatchObject({ text: 'Out ✓', price: 112.5 });
  });

  it('layoutBreaks keeps only the IB chip', () => {
    const out = layoutBreaks([{ timestamp_ms: OPEN, ib_box_h: 10, ib_box_l: 5 }], [], [], rates, { kind: 'breaks' }, 'America/Los_Angeles', OPEN / 1000);
    expect(out.tags.every((t) => t.id.startsWith('breaks-ib'))).toBe(true);
  });
});
