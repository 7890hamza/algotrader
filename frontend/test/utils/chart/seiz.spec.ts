import { describe, expect, it } from 'vitest';

import { dashCell, layoutSeiz, readSeizGuide, type SeizGuide } from '@/utils/chart/seiz';

const guide = {
  kind: 'seiz',
  source: 'test',
  timeframes: [{ key: '1h', label: '1h' }],
  zones: {
    eh: { name: 'External high', where: 'Above the last high', color: '#C2475B' },
    ih: { name: 'Internal high', where: 'Inside the last range', color: '#8E3442' },
    il: { name: 'Internal low', where: 'Inside the last range', color: '#2F5F96' },
    el: { name: 'External low', where: 'Below the last low', color: '#1C9D7C' },
  },
  bands: [
    { pct: 50, label: '50th', alpha: 0.16, odds: '50% had already stopped' },
    { pct: 75, label: '75th', alpha: 0.26, odds: '75% had already stopped' },
    { pct: 85, label: '85th', alpha: 0.38, odds: '15% went further' },
    { pct: 99, label: '99th ✕', alpha: 0.55, odds: '1% went further' },
  ],
  stat: { color: '#C8A27A', text: '' },
};

const H = 3_600_000;
const start = Date.UTC(2026, 10, 12, 15); // 10:00 New York
const point = (min: number, extra: Record<string, number>) => ({
  timestamp_ms: start + min * 60_000, start, end: start + H, open: 100, ph: 110, pl: 90, ...extra,
});
const inside = { ih50: 102, ih75: 104, ih85: 105, ih99: 109, il50: 98, il75: 96, il85: 95, il99: 91 };
const broke = { eh50: 111, eh75: 112, eh85: 113, eh99: 118, il50: 98, il75: 96, il85: 95, il99: 91 };

describe('SEIZ layout', () => {
  it('reads the guide', () => {
    expect(readSeizGuide(guide as never)).not.toBeNull();
    expect(readSeizGuide({ kind: 'other' } as never)).toBeNull();
  });

  it('stacks four bands per zone, labelled at the outer edge, deeper further out', () => {
    const points = [point(0, inside), point(1, inside), point(2, broke), point(3, broke)];
    const boxes = layoutSeiz(points as never, guide as unknown as SeizGuide, { zoneLabel: '1h', barSeconds: 60 });
    const ih = boxes.filter((b) => b.id.startsWith('seiz-ih'));
    expect(ih.map((b) => [b.low, b.high, b.edgeLabel])).toEqual([[100, 102, '50th'], [102, 104, '75th'], [104, 105, '85th'], [105, 109, '99th ✕']]);
    expect(ih[0].fillOpacity).toBeLessThan(ih[3].fillOpacity!);
    // internal high stops at the bar before the break; external high starts at the break bar
    expect(ih[0].endTime).toBe((start + 60_000) / 1000);
    const eh = boxes.filter((b) => b.id.startsWith('seiz-eh'));
    expect(eh[0]).toMatchObject({ low: 110, high: 111, startTime: (start + 120_000) / 1000 });
    // the running candle's zones reach to the end of the candle
    expect(eh[0].endTime).toBe((start + H) / 1000 - 60);
    const il = boxes.filter((b) => b.id.startsWith('seiz-il'));
    expect(il[0]).toMatchObject({ high: 100, low: 98, edgeAt: 'bottom' });
    expect(boxes.some((b) => b.rule)).toBe(true);
  });

  it('draws the Stat Zone when present', () => {
    const p = point(0, { ...inside, st_h_lo: 101, st_h_mid: 103, st_h_hi: 106, st_l_hi: 99, st_l_mid: 97, st_l_lo: 94 });
    const boxes = layoutSeiz([p] as never, guide as unknown as SeizGuide, { zoneLabel: '1h', barSeconds: 60 });
    const stat = boxes.filter((b) => b.id.startsWith('seiz-stat'));
    expect(stat).toHaveLength(2);
    expect(stat[0]).toMatchObject({ high: 106, low: 101, midline: 103, outline: true });
  });

  it('writes dashboard cells like SEIZ', () => {
    expect(dashCell(185)).toBe('85 Ext');
    expect(dashCell(100)).toBe('<50 Ext');
    expect(dashCell(75)).toBe('75 Int');
    expect(dashCell(0)).toBe('–');
  });
});
