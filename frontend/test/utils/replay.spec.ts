import { describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useReplayStore } from '@/stores/replayStore';
import { cmeDayStartMs, replayUrl } from '@/utils/replay';

describe('replay', () => {
  it('builds the replay link and the CME day start', () => {
    expect(replayUrl(123, 'http://x/?pane=2')).toBe('http://x/?pane=2&replay=123');
    expect(replayUrl(null, 'http://x/?pane=2&replay=123')).toBe('http://x/?pane=2');
    expect(new Date(cmeDayStartMs('2026-11-20')).toISOString()).toBe('2026-11-19T23:00:00.000Z'); // 6 PM EST
  });

  it('steps and jumps through the loaded bars', () => {
    setActivePinia(createPinia());
    const r = useReplayStore();
    r.barTimes = [0, 60_000, 120_000, 3_600_000, 3_660_000];
    r.cursorMs = 0;
    r.step(1);
    expect(r.cursorMs).toBe(60_000);
    r.step(-5);
    expect(r.cursorMs).toBe(0);
    r.jump(3_600_000);
    expect(r.cursorMs).toBe(3_600_000);
    r.step(10);
    expect(r.atEnd).toBe(true);
  });
});
