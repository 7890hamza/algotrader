import { describe, expect, it } from 'vitest';

import { buildRangeBar } from '@/utils/chart/rangeBar';

describe('buildRangeBar', () => {
  it('uses the latest day range from MTF SDEV outputs', () => {
    const bar = buildRangeBar(
      [
        { timestamp_ms: 2_000, dr_h: 7853.75, dr_l: 7817, dr_mid: 7835.38, adr: 74.22 },
        { timestamp_ms: 1_000, dr_h: 7850, dr_l: 7820, dr_mid: 7835 },
      ],
      { kind: 'mtf_sdev', rangeColor: '#378ADD' },
    );
    expect(bar).toEqual({ time: 2, high: 7853.75, low: 7817, mid: 7835.38, adr: 74.22, color: '#378ADD' });
  });

  it('is off for other indicators or without range outputs', () => {
    expect(buildRangeBar([{ timestamp_ms: 1, dr_h: 1, dr_l: 0 }], { kind: 'breaks' })).toBeNull();
    expect(buildRangeBar([{ timestamp_ms: 1 }], { kind: 'mtf_sdev' })).toBeNull();
  });
});
