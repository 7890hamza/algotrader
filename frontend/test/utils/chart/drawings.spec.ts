import { describe, expect, it } from 'vitest';

import { distToSegment, logicalToTime, magnet, rayEnd, timeToLogical, touches } from '@/utils/chart/drawings';

const M = 60_000;
const times = [0, M, 2 * M, 10 * M, 11 * M]; // a gap between bar 2 and bar 3

describe('drawings helpers', () => {
  it('turns times into bar positions and back, across gaps and past the last bar', () => {
    expect(timeToLogical(times, M, 0)).toBe(0);
    expect(timeToLogical(times, M, 1.5 * M)).toBe(1.5);
    expect(timeToLogical(times, M, 5 * M)).toBe(3); // inside the gap: sits on the next bar
    expect(timeToLogical(times, M, 13 * M)).toBe(6);
    expect(timeToLogical(times, M, -2 * M)).toBe(-2);
    for (const l of [0, 0.5, 1.25, 3, 4, 7.5, -1]) expect(timeToLogical(times, M, logicalToTime(times, M, l))).toBeCloseTo(l);
  });

  it('counts touches of a level after it was drawn, one per visit', () => {
    const bars = [
      { t: 0, h: 105, l: 99 }, // before the line: ignored
      { t: 1, h: 101, l: 95 }, { t: 2, h: 102, l: 99 }, // one visit over two bars
      { t: 3, h: 98, l: 90 },
      { t: 4, h: 100.5, l: 97 }, // back again
    ];
    expect(touches(bars, 100, 0)).toBe(2);
    expect(touches(bars, 200, 0)).toBe(0);
  });

  it('measures how close a click is to a line and cuts rays at the edge', () => {
    expect(distToSegment(5, 3, 0, 0, 10, 0)).toBe(3);
    expect(distToSegment(15, 0, 0, 0, 10, 0)).toBe(5);
    expect(rayEnd(0, 0, 10, 10, 100)).toEqual([100, 100]);
    expect(rayEnd(50, 0, 40, 10, 100)).toEqual([0, 50]);
  });

  it('snaps to the nearest open / high / low / close when close enough', () => {
    const bar = { o: 100, h: 104, l: 98, c: 103 };
    expect(magnet(103.6, bar, 1)).toBe(104);
    expect(magnet(101, bar, 0.5)).toBe(101);
  });
});
