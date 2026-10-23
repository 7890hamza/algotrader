import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint, IndicatorOutputMetadata } from '@/types/contracts';
import {
  buildSessionLevelSegments,
  firstTouchTime,
  formatLevelPrice,
  hasLevelOutputs,
  upsertIndicatorPoint,
} from '@/utils/chart/sessionLevels';

const outputs: Record<string, IndicatorOutputMetadata> = {
  open: { type: 'level', label: 'Open', plotOptions: { color: '#E8B04F', lineWidth: 2 } },
  '+1': {
    type: 'level',
    label: '+1',
    touch: 'high',
    plotOptions: { color: '#26A69A', lineWidth: 2, lineStyle: 0 },
  },
  '-0.25': {
    type: 'level',
    label: '-0.25',
    touch: 'low',
    plotOptions: { color: '#EF5350', lineWidth: 1, lineStyle: 2 },
  },
};

const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

function session(startMs: number, bars: number, open: number, plus: number, minus: number | null) {
  return Array.from({ length: bars }, (_, i): IndicatorDataPoint => ({
    timestamp_ms: startMs + i * MINUTE_MS,
    open,
    '+1': plus,
    '-0.25': minus,
  }));
}

describe('sessionLevels', () => {
  it('builds one segment per session and level, breaking between sessions', () => {
    const day1 = session(1_000 * MINUTE_MS, 240, 100, 101, 99.75);
    const day2 = session(1_000 * MINUTE_MS + DAY_MS, 240, 110, 111.5, null);
    const segments = buildSessionLevelSegments([...day2, ...day1], outputs);

    const opens = segments.filter((s) => s.label === 'Open');
    expect(opens).toHaveLength(2);
    expect(opens[0]).toMatchObject({ price: 100, startTime: 60_000, endTime: 60_000 + 239 * 60 });
    expect(opens[1].price).toBe(110);
    expect(segments.filter((s) => s.label === '-0.25')).toHaveLength(1);

    const minus = segments.find((s) => s.label === '-0.25');
    expect(minus).toMatchObject({ lineStyle: 2, lineWidth: 1, color: '#EF5350', touch: 'low' });
  });

  it('applies style overrides from indicator settings', () => {
    const data = session(0, 3, 100, 101, 99);
    const [open] = buildSessionLevelSegments(data, outputs, { open: { color: '#ffffff' } });
    expect(open.color).toBe('#ffffff');
  });

  it('detects level outputs and formats prices', () => {
    expect(hasLevelOutputs(outputs)).toBe(true);
    expect(hasLevelOutputs({ sma: { type: 'line' } })).toBe(false);
    expect(formatLevelPrice(7801.3125)).toBe('7,801.31');
  });

  it('finds the first candle that touched a level inside its segment', () => {
    const [plus] = buildSessionLevelSegments(session(0, 5, 100, 101, null), {
      '+1': outputs['+1'],
    });
    const candles = [
      { time: -60, high: 200, low: 0 }, // before the segment
      { time: 0, high: 100.5, low: 99 },
      { time: 60, high: 101, low: 100 },
      { time: 120, high: 102, low: 100 },
    ];
    expect(firstTouchTime(plus, candles)).toBe(60);
    expect(firstTouchTime({ ...plus, price: 150 }, candles)).toBeNull();
  });

  it('upserts live points by timestamp', () => {
    const points: IndicatorDataPoint[] = [{ timestamp_ms: 1, open: 1 }, { timestamp_ms: 3, open: 3 }];
    upsertIndicatorPoint(points, { timestamp_ms: 3, open: 30 });
    upsertIndicatorPoint(points, { timestamp_ms: 2, open: 2 });
    upsertIndicatorPoint(points, { timestamp_ms: 4, open: 4 });
    expect(points.map((p) => p.open)).toEqual([1, 2, 30, 4]);
  });
});
