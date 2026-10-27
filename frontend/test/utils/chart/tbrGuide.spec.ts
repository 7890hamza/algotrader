import { describe, expect, it } from 'vitest';

import { buildTbrGuideView } from '@/utils/chart/tbrGuide';

const T = Date.UTC(2026, 5, 25, 12, 30); // 8:30 New York, 5:30 Pacific
const rates = { '1,0': [80.8, 797] as [number, number], '1,1': [67.9, 355] as [number, number] };
const base = {
  timestamp_ms: T, open: 7541.5, '+0.25': 7552.25, '-0.25': 7530.75,
  stretch_near: 7559.78, stretch_mid: 7569.41, stretch_far: 7583.69,
  follow_near: 7513.85, follow_mid: 7492.43, follow_far: 7457.55,
};

describe('buildTbrGuideView', () => {
  it('waits for a touch', () => {
    const view = buildTbrGuideView({ timestamp_ms: T, open: 7541.5, '+0.25': 7552.25, '-0.25': 7530.75 }, rates, 'America/Los_Angeles')!;
    expect(view.sentence).toContain('Waiting for price to touch +0.25 (7,552.25)');
    expect(view.tone).toBe('waiting');
  });

  it('reads the stretch after a first-hour +0.25 hit', () => {
    const view = buildTbrGuideView({ ...base, touch_side: 1, touch_at: T, stretch_now: 7561.75 }, rates, 'America/Los_Angeles')!;
    expect(view.sentence).toBe('+0.25 hit at 5:30 AM. Mornings like this came back to the AM TBR Open 81% of the time.');
    expect(view.detail).toContain('between the median and P75');
    const deep = buildTbrGuideView({ ...base, touch_side: 1, touch_at: T, stretch_now: 7590 }, rates, 'America/Los_Angeles')!;
    expect(deep.tone).toBe('warn');
    expect(deep.detail).toContain('no-return');
  });

  it('reads the follow-through after the return', () => {
    const view = buildTbrGuideView({ ...base, touch_side: 1, touch_at: T, revert_at: T + 62 * 60000, follow_now: 7456.25 }, rates, 'America/Los_Angeles')!;
    expect(view.sentence).toContain('Back at the AM TBR Open at 6:32 AM');
    expect(view.detail).toContain('past P90');
    expect(`${view.sentence} ${view.detail}`).not.toMatch(/\b(buy|sell)\b/i);
  });

  it('is hidden outside the window', () => {
    expect(buildTbrGuideView({ timestamp_ms: T, open: null }, rates, 'UTC')).toBeNull();
  });
});
