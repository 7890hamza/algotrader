import { describe, expect, it } from 'vitest';

import type { IndicatorDataPoint, IndicatorOutputMetadata } from '@/types/contracts';
import {
  buildAlnGuideLines,
  buildGuideView,
  buildSessionBoxes,
  inWords,
  readGuideConfig,
} from '@/utils/chart/alnGuide';

const MIN = 60_000;
const T0 = Date.UTC(2026, 9, 21, 12, 0); // 5:00 AM Pacific

const stats = {
  P3: { n: 600, high: 74, low: 30, high_first: 70, low_after_high_first: 20, high_after_low_first: 40, neither: 10 },
  P4: { n: 600, high: 30, low: 76, high_first: 30, low_after_high_first: 40, high_after_low_first: 20, neither: 10 },
};
const config = readGuideConfig({ kind: 'aln', stats, colors: { watch: '#e9c46a', other: '#56606b' } })!;

const outputs: Record<string, IndicatorOutputMetadata> = {
  asia_high: { type: 'box', box: 'asia', edge: 'high', label: 'Asia', plotOptions: { color: '#e0574a' } },
  asia_low: { type: 'box', box: 'asia', edge: 'low', label: 'Asia', plotOptions: { color: '#e0574a' } },
};

function nyPoint(i: number, extra: Partial<IndicatorDataPoint> = {}): IndicatorDataPoint {
  return {
    timestamp_ms: T0 + i * MIN,
    pattern: 4,
    ref_london_high: 7010,
    ref_london_low: 6990,
    ny_open: 7000,
    sdev_pts: 21,
    up_at: null,
    dn_at: null,
    recent_1: 411,
    recent_2: 301,
    recent_3: 100,
    ...extra,
  };
}

describe('alnGuide', () => {
  it('reads plain-language odds', () => {
    expect(inWords(74)).toBe('about 3 out of 4 days');
    expect(inWords(50)).toBe('about 1 out of 2 days');
  });

  it('builds one box per session from running ranges', () => {
    const points = [
      { timestamp_ms: 0, asia_high: 10, asia_low: 9 },
      { timestamp_ms: MIN, asia_high: 11, asia_low: 9 },
      { timestamp_ms: 2 * MIN, asia_high: 11, asia_low: 8 },
      { timestamp_ms: 3 * MIN, asia_high: null, asia_low: null },
      { timestamp_ms: 4 * MIN, asia_high: 20, asia_low: 19 },
    ];
    const boxes = buildSessionBoxes(points, outputs);
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toMatchObject({ startTime: 0, endTime: 120, high: 11, low: 8, label: 'Asia', color: '#e0574a' });
  });

  it('marks the London low as the watch line on a P4 day', () => {
    const lines = buildAlnGuideLines([nyPoint(0), nyPoint(1)], config);
    const low = lines.find((line) => line.price === 6990)!;
    const high = lines.find((line) => line.price === 7010)!;
    expect(low.label).toBe('Watch · London low');
    expect(low.color).toBe('#e9c46a');
    expect(high.label).toBe('Changes the story · London high');
    expect(high.lineStyle).toBe(2);
  });

  it('walks through a P4 day without saying buy or sell', () => {
    const watching = buildGuideView([nyPoint(0)], config, 'America/Los_Angeles');
    expect(watching.sentence).toContain("New York usually reaches London's low (6,990.00), about 3 out of 4 days");
    expect(watching.tone).toBe('live');
    expect(watching.steps.find((s) => s.state === 'current')?.key).toBe('watch');
    expect(watching.checks[1].state).toBe('yes');
    expect(watching.checks[2].answer).toContain('-0.5 line');
    expect(watching.recent.map((d) => d.kind)).toEqual(['hit', 'miss', 'flat']);

    const done = buildGuideView([nyPoint(0), nyPoint(30, { dn_at: T0 + 30 * MIN })], config, 'America/Los_Angeles');
    expect(done.sentence).toBe("Done: London's low was reached at 5:30 AM.");
    expect(done.tone).toBe('done');

    const changed = buildGuideView([nyPoint(0), nyPoint(10, { up_at: T0 + 10 * MIN })], config, 'America/Los_Angeles');
    expect(changed.sentence).toContain("London's high broke first, at 5:10 AM");
    expect(changed.tone).toBe('changed');

    for (const view of [watching, done, changed]) {
      expect(`${view.sentence} ${view.checks.map((c) => c.answer).join(' ')}`).not.toMatch(/\b(buy|sell)\b/i);
    }
  });

  it('describes Asia while it forms', () => {
    const view = buildGuideView([{ timestamp_ms: 0, asia_high: 7005, asia_low: 6995 }], config, 'UTC');
    expect(view.phase).toBe('asia');
    expect(view.sentence).toBe("Asia is setting tonight's range: 6,995.00 to 7,005.00.");
  });
});
