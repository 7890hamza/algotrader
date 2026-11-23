import { describe, expect, it } from 'vitest';

import { cmeClock, ptClock, readDays, scoreDays, type DcBar } from '@/utils/dailyCandle';

import raw from '../fixtures/es_nov12_13_m5.json';

const bars: DcBar[] = (raw as number[][]).map(([t, o, h, l, c]) => ({ t, o, h, l, c }));

describe('daily candle reads (ES 5-minute, Nov 12-13 2026)', () => {
  it('puts bars on the right CME day and clock', () => {
    expect(cmeClock(Date.parse('2026-11-12T23:00:00Z'))).toEqual({ day: '2026-11-13', dm: 0 }); // 6 PM NY
    expect(cmeClock(Date.parse('2026-11-13T14:30:00Z')).dm).toBe(930); // 9:30 NY
    expect(ptClock(930)).toBe('6:30 AM');
    expect(ptClock(0)).toBe('3 PM');
  });

  const days = readDays(bars, 5);
  const d13 = days.find((d) => d.day === '2026-11-13')!;
  const d12 = days.find((d) => d.day === '2026-11-12')!;

  it("matches the Python study's levels", () => {
    expect(d13.austin.p12).toEqual({ hi: 7649.75, lo: 7598.5 });
    expect(d13.austin.midnightOpen).toBe(7615.75);
    expect(d13.austin.q1).toEqual({ hi: 7646.25, lo: 7623.75 });
    expect(d13.austin.high?.price).toBe(7669.25);
    expect(d13.austin.low?.price).toBe(7598.5);
    expect(d13.austin.low?.inStat).toBe(true);
    expect(d13.austin.high?.inStat).toBe(false);
    expect(d13.riley.openBox).toEqual({ hi: 7643.5, lo: 7580.75 });
    expect(d13.riley.sixBox).toEqual({ hi: 7636.75, lo: 7623.75 });
    expect(d13.riley.asia).toBe(-1);
    expect(d13.riley.london).toBe(1);
    expect(d13.riley.brk).toMatchObject({ dm: 965, dir: -1, edge: 7580.75 });
    expect(d12.riley.brk).toMatchObject({ dm: 1015, dir: 1 });
    expect(d12.riley.night).toBe('trending');
  });

  it('makes the calls and grades them at 1 PM PT', () => {
    // Nov 13: low in stat -> Austin looks up; the low broke and price fell
    expect(d13.austin.lean).toBe(1);
    expect(d13.austin.verdict).toBe('wrong');
    // contradicting night -> Riley fades the down break; price closed back inside the box (False)
    expect(d13.riley.call).toBe('fade');
    expect(d13.riley.held).toBe(false);
    expect(d13.riley.verdict).toBe('right');
    // Nov 12: neither extreme in stat -> no call
    expect(d12.austin.verdict).toBe('no-call');
    expect(scoreDays(days).austin.calls).toBe(1);
  });

  it('only uses bars up to the Replay cursor', () => {
    const at645 = Date.parse('2026-11-13T14:45:00Z'); // 6:45 AM PT
    const d = readDays(bars, 5, at645).find((x) => x.day === '2026-11-13')!;
    expect(d.done).toBe(false);
    expect(d.austin.lean).toBe(1);
    expect(d.austin.verdict).toBe('pending');
    expect(d.riley.openBox).toBeNull(); // the box isn't finished at 6:45
    expect(d.riley.verdict).toBe('pending');
  });
});
