import { describe, expect, it } from 'vitest';
import { statsLadder } from '../../src/utils/setups';

const L = (price: number, hitAt: number | null = null, group = 'Asia') =>
  ({ group, price, kind: 'target', hitAt, never: false, frm: 0, until: 1e15 });

describe('statsLadder', () => {
  it('measures the next open stat each way and counts per tier', () => {
    const r = statsLadder([L(110), L(130), L(220), L(95), L(105, 5), L(140, null, 'Hour')], 10, 100, [25, 100]);
    expect(r.up.next).toBe(10);                  // 105 was already hit at t=5; Hour groups skipped
    expect(r.up.counts).toEqual([1, 2]);         // 110 within 25; 110, 130 within 100
    expect(r.down.next).toBe(5);
    expect(r.down.counts).toEqual([1, 1]);
  });
  it('returns null when nothing is open on a side', () => {
    expect(statsLadder([L(120)], 0, 100, [25]).down.next).toBeNull();
  });
});
