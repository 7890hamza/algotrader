import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint } from '@/types/contracts';
import { buildHourTags } from '@/utils/chart/hourStats';

const T = Date.UTC(2026, 9, 22, 13, 0); // 9:00 New York, 6:00 Pacific
const M = 60_000;
const hours = { '9': { n: 2257, rev: 74.3, segs: { '0': [85.8, 1200], '1': [65.9, 907], '2': [34.0, 150] } } } as never;
const base = { open: 7720, ph: 7725, pl: 7712, setup: 1 };

describe('buildHourTags', () => {
  it('tells the story of a breach that came back', () => {
    const points: IndicatorDataPoint[] = [
      { timestamp_ms: T, ...base },
      { timestamp_ms: T + 25 * M, ...base, side: 1, seg: 1, breach_at: T + 25 * M, stretch_near: 7727.9, stretch_far: 7737.5, follow_near: 7710, follow_far: 7687 },
      { timestamp_ms: T + 40 * M, ...base, side: 1, seg: 1, breach_at: T + 25 * M, revert_at: T + 40 * M },
      { timestamp_ms: T + 60 * M, open: 7718, ph: 7730, pl: 7715, setup: 0 },
    ];
    const [tag, next] = buildHourTags(points, hours, 'America/Los_Angeles');
    expect(tag.date).toBe('6 AM');
    expect(tag.chipText).toBe('H · 66%');
    expect(tag.result).toBe('reached');
    expect(tag.lines[0]).toBe('Broke the prior hour high 7,725.00 at 6:25 AM (minutes 20-39)');
    expect(tag.lines.at(-1)).toBe('Came back to the hour open 7,720.00 at 6:40 AM');
    expect(next.chipText).toBe('no setup');
  });
});
