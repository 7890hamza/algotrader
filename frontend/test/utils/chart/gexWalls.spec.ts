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
