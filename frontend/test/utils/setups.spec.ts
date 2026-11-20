import { describe, expect, it } from 'vitest';

import { cmeDay, cmeDayBounds, hitStacks, openStacks, scoreSetups, tradesFrom } from '@/utils/setups';

describe('setups', () => {
  const entry = Date.UTC(2026, 8, 17, 6, 30); // 2:30 AM New York
  const points = [
    { timestamp_ms: entry, A_dir: null, B_dir: 1, B_entry: 7671.25, B_exit_ms: entry + 37 * 60_000, B_pts: 9.5, B_how: 1, B_l1: 7624, B_l2: null },
    { timestamp_ms: entry + 3_600_000, D_dir: -1, D_entry: 7680, D_exit_ms: entry + 3_700_000, D_pts: -3.5, D_how: -1, D_l1: 7690, D_l2: 7682 },
  ];

  it('turns engine rows into trades with their trigger levels', () => {
    const trades = tradesFrom(points as never);
    expect(trades.map((t) => [t.id, t.dir, t.how, t.pts])).toEqual([['B', 1, 'target', 9.5], ['D', -1, 'stop', -3.5]]);
    expect(trades[0].levels).toEqual([{ name: 'Day open', price: 7624 }]);
    expect(trades[1].levels.map((l) => l.name)).toEqual(['Day −1 SD', 'Last hour low']);
  });

  it('scores each setup', () => {
    const s = scoreSetups(tradesFrom(points as never));
    expect(s.find((x) => x.id === 'B')).toMatchObject({ trades: 1, hitRate: 1, pts: 9.5 });
    expect(s.find((x) => x.id === 'A')).toMatchObject({ trades: 0 });
  });

  it('uses the CME day (6 PM to 5 PM New York)', () => {
    expect(cmeDay(Date.UTC(2026, 8, 16, 23, 0))).toBe('2026-09-17'); // 7 PM Sep 16 NY
    expect(cmeDay(Date.UTC(2026, 8, 17, 20, 0))).toBe('2026-09-17'); // 4 PM Sep 17 NY
    const { startMs, endMs } = cmeDayBounds('2026-09-17');
    expect(new Date(startMs).toISOString()).toBe('2026-09-16T22:00:00.000Z'); // 6 PM EDT
    expect(new Date(endMs).toISOString()).toBe('2026-09-17T21:00:00.000Z'); // 5 PM EDT
    expect(new Date(cmeDayBounds('2026-01-15').startMs).toISOString()).toBe('2026-01-14T23:00:00.000Z'); // EST
  });
});

describe('stacked stats', () => {
  const L = (label: string, price: number, hitMin: number | null, odds = 50) =>
    ({ label, price, odds, hitAt: hitMin === null ? null : hitMin * 60_000, frm: 0, until: 10_000 * 60_000, never: false });
  const candles = Array.from({ length: 30 }, (_, i) => {
    const t = i * 300; // 5-minute bars from minute 0
    const close = i < 10 ? 7060 - i * 2 : 7040 + (i - 10) * 1.5; // falls into 7040, then comes back
    return { time: t, high: close + 1, low: close - 1, close };
  });

  it('finds levels hit together and how far price came back', () => {
    const levels = [L('PM -1 SD', 7041, 50), L('9 AM MAE P90', 7040.5, 52), L('TBR -0.25', 7040, 53), L('far', 7000, 54)];
    const [s] = hitStacks(levels, candles, 3, 3);
    expect(s.count).toBe(3);
    expect(s.approach).toBe(1);               // came down into it, so reverting means up
    expect(s.back).toBeGreaterThan(10);
    expect(hitStacks(levels, candles, 3, 4)).toHaveLength(0);
  });

  it('lists open stacks ahead of price, nearest first', () => {
    const levels = [L('A', 7030, null, 30), L('B', 7031.5, null, 16), L('C', 7032, null, 7), L('D', 7100, null), L('E', 7101, null), L('F', 7012, null)];
    const s = openStacks(levels, 0, 7040, 3, 2);
    expect(s.map((x) => [x.lo, x.hi, x.count, x.away])).toEqual([[7030, 7032, 3, 8], [7100, 7101, 2, 60]]);
    expect(s[0].labels[0]).toBe('A 30%');
  });
});
