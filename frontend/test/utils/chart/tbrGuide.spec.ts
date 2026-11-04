import { describe, expect, it } from 'vitest';
import type { IndicatorDataPoint } from '@/types/contracts';

import { activeTbrSession, buildTbrGuideView } from '@/utils/chart/tbrGuide';

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
    expect(view.sentence).toBe('+0.25 hit at 5:30 AM. Sessions like this came back to the AM TBR Open 81% of the time.');
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

describe('ALN TBR sessions', () => {
  it('walks through the CME session with its own name and hours', () => {
    const t = Date.UTC(2026, 10, 3, 23, 10); // 18:10 New York, 3:10 PM Pacific
    const points: IndicatorDataPoint[] = [
      { timestamp_ms: t - 60_000, am_open: 7600 },
      {
        timestamp_ms: t,
        cme_open: 7610, cme_up: 7615.25, cme_dn: 7604.75, cme_side: 1, cme_touch_at: t - 5 * 60_000,
        cme_stretch_near: 7619, cme_stretch_mid: 7623, cme_stretch_far: 7630, cme_stretch_now: 7617,
      },
    ];
    const active = activeTbrSession(points, [{ key: 'am', label: 'AM' }, { key: 'cme', label: 'CME' }])!;
    expect(active.key).toBe('cme');
    expect(active.point['+0.25']).toBe(7615.25);
    const view = buildTbrGuideView(active.point, { '1,0': [74.7, 1269] }, 'America/Los_Angeles', { label: 'CME TBR', startHour: 18 })!;
    expect(view.sentence).toBe('+0.25 hit at 3:05 PM. Sessions like this came back to the CME TBR Open 75% of the time.');
  });
});
