import { describe, expect, it } from 'vitest';

import { findNaps } from '@/utils/cmeNap';

const M = 60_000;
const bars = (from: number, n: number) => Array.from({ length: n }, (_, i) => ({ timestamp_ms: from + i * M, open: 100, close: 100 }));

describe('findNaps', () => {
  it('finds one closure per gap', () => {
    const c = [...bars(0, 120), ...bars(180 * M, 60), ...bars(24 * 60 * M, 60)];
    expect(findNaps(c, M).map((n) => [n.closeT / M, n.openT / M])).toEqual([[119, 180], [239, 1440]]);
  });

  it('a stray candle inside a closure does not split it', () => {
    const stray = { timestamp_ms: 150 * M, open: 99, close: 99 };
    const c = [...bars(0, 120), stray, ...bars(180 * M, 60)];
    const naps = findNaps(c, M);
    expect(naps).toHaveLength(1);
    expect([naps[0].closeT / M, naps[0].openT / M]).toEqual([119, 180]);
  });

  it('marks long closures as weekends', () => {
    const c = [...bars(0, 60), ...bars(49 * 60 * M, 60)];
    expect(findNaps(c, M)[0].weekend).toBe(true);
  });
});
