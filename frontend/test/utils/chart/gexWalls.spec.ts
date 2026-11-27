import { describe, expect, it } from 'vitest';

import { gexMarket, wallSteps, type WallSnap } from '@/utils/chart/gexLink';

const snap = (t: number, call: number | null): WallSnap => ({ t, call, outerCall: null, flip: null, put: null, outerPut: null, etf: 'QQQ', ratio: 41, expirations: [] });

describe('option walls', () => {
  it('joins refreshes that kept the same level and steps when it moves', () => {
    const s = [snap(0, 100), snap(5, 100), snap(10, 110), snap(15, null), snap(20, 110)];
    expect(wallSteps(s, 'call', 30)).toEqual([[0, 10, 100], [10, 15, 110], [20, 30, 110]]);
  });
  it('maps micros to their market', () => {
    expect(gexMarket('MNQ')).toBe('NQ');
    expect(gexMarket('ES')).toBe('ES');
    expect(gexMarket('BTC')).toBeNull();
  });
});

describe('VWAP from the 9:30 New York open', () => {
  it('uses (O+H+L+C)/4 weighted by volume, restarts each day, and skips bars outside 9:30-4 PM', async () => {
    const { rthVwap } = await import('@/utils/chart/gexLink');
    const t930 = Date.UTC(2026, 10, 25, 14, 30); // 9:30 AM New York (EST)
    const bars = [
      { t: t930 - 60_000, o: 1, h: 1, l: 1, c: 1, v: 999 },          // 9:29: before the open
      { t: t930, o: 100, h: 104, l: 96, c: 100, v: 10 },             // price 100
      { t: t930 + 60_000, o: 110, h: 112, l: 108, c: 110, v: 30 },   // price 110
      { t: t930 + 86_400_000, o: 50, h: 50, l: 50, c: 50, v: 5 },    // next day: starts over
    ];
    const v = rthVwap(bars);
    expect(v[0]).toBeNull();
    expect(v[1]).toBe(100);
    expect(v[2]).toBe(107.5); // (100*10 + 110*30) / 40
    expect(v[3]).toBe(50);
  });
});
