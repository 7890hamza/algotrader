import { describe, expect, it } from 'vitest';
import { runFades } from '../../src/utils/setups';

const M = 60_000;
const lvl = (price: number, hitAt: number) => ({ group: 'Asia', label: `s${price}`, price, kind: 'target', hitAt, never: false, side: 'up' as const, frm: 0, until: 1e15 });
const bar = (i: number, h: number, l: number, c: number) => ({ timestamp_ms: i * M, high: h, low: l, close: c });
const S = { minCount: 4, trigger: 0.25, target: 0.5, pad: 1, maxHoldMs: 6 * 3600_000 };

describe('runFades', () => {
  // run up through 100,110,120,130 (box 100-130), extreme 132, then a close at 121 (< 130 - 7.5)
  const levels = [lvl(100, 1 * M), lvl(110, 2 * M), lvl(120, 3 * M), lvl(130, 4 * M)];
  const bars = [bar(1, 101, 99, 100), bar(2, 111, 100, 110), bar(3, 121, 110, 120), bar(4, 132, 120, 131),
    bar(5, 131, 125, 126), bar(6, 126, 120, 121), bar(7, 121, 105, 108)];
  it('enters short on the give-back and takes the target halfway to the base', () => {
    const [f] = runFades(levels, bars, 7 * M, 1e15, S);
    expect(f.dir).toBe(-1);
    expect(f.entry).toBe(121);
    expect(f.stop).toBe(133);          // run extreme 132 + 1
    expect(f.target).toBe(110.5);      // halfway from 121 to 100
    expect(f.how).toBe('target');
    expect(f.pts).toBeCloseTo(10.5);
  });
  it('shows an open trade before it has finished', () => {
    const [f] = runFades(levels, bars, 6 * M, 1e15, S);
    expect(f.how).toBeNull();
  });
  it('needs enough stats in the run', () => {
    expect(runFades(levels, bars, 7 * M, 1e15, { ...S, minCount: 8 })).toHaveLength(0);
  });
});
