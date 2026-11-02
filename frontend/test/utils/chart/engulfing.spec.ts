import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint } from '@/types/contracts';
import { buildEngulfingLines, buildEngulfingMarks, buildMaruMarks } from '@/utils/chart/engulfing';

const T = Date.UTC(2026, 9, 12, 13, 30); // 6:30 Pacific
const M = 5 * 60_000;
const points: IndicatorDataPoint[] = [
  { timestamp_ms: T, signal: -1, body_top: 6800, body_bot: 6794, inval_bear: 6800, mae: 1, mfe: 9, outcome: 1 },
  { timestamp_ms: T + M, inval_bear: 6800 },
  { timestamp_ms: T + 2 * M, inval_bear: 6800 },
  { timestamp_ms: T + 3 * M, signal: 1, body_top: 6790, body_bot: 6785, inval_bull: 6785, mae: 6, mfe: 2, outcome: -1, inval_at: T + 4 * M },
  { timestamp_ms: T + 4 * M, inval_bull: 6785 },
];

describe('engulfing marks', () => {
  it('flags the candle that formed at another level and explains the result', () => {
    const levels = [{ price: 6801, label: 'London H', startTime: T / 1000 - 3600, endTime: T / 1000 + 3600 }];
    const marks = buildEngulfingMarks(points, levels);
    expect(marks).toHaveLength(2);
    expect(marks[0].atLevel).toBe('London H');
    expect(marks[0].lines[0]).toContain('Bearish engulfing · 6:30 AM · at London H');
    expect(marks[0].lines.at(-1)).toContain('✓');
    expect(marks[1].atLevel).toBeNull();
    expect(marks[1].lines.at(-1)).toBe('✕ Invalidated at 6:50 AM');
  });

  it('draws invalidation lines only for candles at a level or still holding', () => {
    const levels = [{ price: 6801, label: 'London H', startTime: T / 1000 - 3600, endTime: T / 1000 + 3600 }];
    const lines = buildEngulfingLines(points, buildEngulfingMarks(points, levels));
    expect(lines).toHaveLength(1);
    expect(lines[0].price).toBe(6800);
    expect(lines[0].endTime).toBe((T + 2 * M) / 1000);
    const live = [...points, { timestamp_ms: T + 5 * M, signal: 1, body_top: 6795, body_bot: 6790, inval_bull: 6790, outcome: 0 }];
    const last = buildEngulfingLines(live, buildEngulfingMarks(live)).at(-1)!;
    expect(last.label).toBe('Bull invalidation');
    expect(last.showPrice).toBe(true);
  });

  it('reads no-wick candles and when price came back', () => {
    const marus = buildMaruMarks([
      { timestamp_ms: T, maru_side: 1, maru_price: 6790, maru_back_at: T + 2 * M },
      { timestamp_ms: T + M, maru_side: -1, maru_price: 6810, maru_back_at: null },
      { timestamp_ms: T + 2 * M, signal: 1 },
    ]);
    expect(marus).toEqual([
      { time: T / 1000, side: 1, price: 6790, backAt: (T + 2 * M) / 1000 },
      { time: (T + M) / 1000, side: -1, price: 6810, backAt: null },
    ]);
  });
});
