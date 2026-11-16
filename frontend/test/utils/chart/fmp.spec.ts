import { describe, expect, it } from 'vitest';

import { curvePath, layoutFmp, parseList, readFmpGuide } from '@/utils/chart/fmp';

const guide = readFmpGuide({ kind: 'fmp', slices: [5, 10, 15, 20, 25, 30], open_color: '#3B82F6', up_color: '#9AA4B2', down_color: '#9AA4B2', odds: { '1': 'Reached in about 1 of 4 hours' } })!;
const start = Date.UTC(2026, 10, 12, 16, 0); // 11:00 New York
const point = (min: number) => ({ timestamp_ms: start + min * 60_000, start, open: 100, ratio: 1, sig5: 2, sig10: 3, sig15: 4, sig20: 5, sig25: 6, sig30: 7 });

describe('fmp', () => {
  it('draws one rail per slice, sigma and side, ending at its slice time', () => {
    const { segments, curves } = layoutFmp([point(0), point(1)], guide, { sigmas: [1], slices: [5, 30], curves: 'curved', hoursBack: 3, barSeconds: 60 });
    const rails = segments.filter((s) => s.id.startsWith('fmp-1'));
    expect(rails.map((s) => s.label)).toEqual(['5m +1σ (11:00)', '30m +1σ (11:00)', '5m -1σ (11:00)', '30m -1σ (11:00)']);
    expect(rails[1].price).toBe(107);
    expect(rails[1].sessionEndTime).toBe(start / 1000 + 1800);
    expect(curves).toHaveLength(2);
    expect(curves[1].points.map((p) => p.price)).toEqual([100, 98, 93]);
  });

  it('keeps only the last hours and parses lists', () => {
    const later = { ...point(60), start: start + 3_600_000 };
    const { segments } = layoutFmp([point(0), later], guide, { sigmas: [1], slices: [30], curves: 'off', hoursBack: 1, barSeconds: 60 });
    expect(segments.every((s) => s.id.includes(String(start / 1000 + 3600)))).toBe(true);
    expect(parseList('1.5, 0.5,x', [1])).toEqual([0.5, 1.5]);
  });

  it('smooths with Catmull-Rom only when asked', () => {
    const pts = [{ x: 0, y: 0 }, { x: 10, y: 5 }, { x: 20, y: 7 }];
    expect(curvePath(pts, false)[1].c1).toBeUndefined();
    expect(curvePath(pts, true)[1].c1).toBeDefined();
  });
});
