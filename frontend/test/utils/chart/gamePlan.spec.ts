import { describe, expect, it } from 'vitest';

import { buildBoard, isCarried, levelOdds, levelStatus, levelTrack, ownOdds, type DayPlan, type PlanLevel } from '@/utils/chart/gamePlan';
import { chartLevels } from '@/utils/chart/gamePlanPrimitive';

const H = 3_600_000;
const S = 0; // 3 PM PT the evening before
const sessions = { asia: [S, S + 8 * H], ldn: [S + 8 * H, S + 14 * H], am: [S + 14 * H, S + 18 * H], pm: [S + 18 * H, S + 23 * H] } as DayPlan['sessions'];

function lv(p: Partial<PlanLevel> & Pick<PlanLevel, 'id' | 'price'>): PlanLevel {
  return { group: 'SDEV', label: p.id, frm: S, origUntil: S + 8 * H, until: S + 23 * H, odds: 56, kind: 'target', hitAt: null, never: false, color: '#fff', ...p };
}

const plan: DayPlan = {
  symbol: 'ES', key: '2026-11-05', label: 'Thu Nov 5', start: S, end: S + 23 * H, sessions,
  last: { t: S + 17 * H, close: 7500 },
  ctx: { rth0: S + 15.5 * H, ib1: S + 16.5 * H, rth1: S + 22 * H, adr: 100, dayOpen: 7700, dayHigh: 7710, dayLow: 7490, rthOpen: 7680, rthHigh: 7690, rthLow: 7495, ethOver: { other_held: 85.2, one_by_close: 64.2 } },
  levels: [
    lv({ id: 'asia_u1', label: 'Asia +1 SD', price: 7720 }), // missed by Asia, carried all day
    lv({ id: 'asia_d1', label: 'Asia -1 SD', price: 7600, hitAt: S + 15 * H }), // missed by Asia and London, hit in NY AM
    lv({ id: 'am_d0.5', label: 'NY AM -0.5 SD', price: 7450, frm: S + 14 * H, origUntil: S + 18 * H, odds: 58.1 }),
    lv({ id: 'y_ibx', label: 'Wed IB 1.18x', price: 7800, odds: null, origUntil: S, fromDay: 'Wed' }),
    lv({ id: 'am_open', label: 'NY AM open', price: 7680, kind: 'open', frm: S + 14 * H, origUntil: S + 18 * H, until: S + 18 * H }),
  ],
};

describe('game plan levels', () => {
  it('knows open, done and carried', () => {
    const t = plan.last!.t;
    const [u1, d1, am, y] = plan.levels;
    expect(levelStatus(u1, t)).toBe('open');
    expect(levelStatus(d1, t)).toBe('done');
    expect(levelStatus(am, S + 10 * H)).toBe('later');
    expect(isCarried(u1, t)).toBe(true);
    expect(isCarried(am, t)).toBe(false);
    expect(isCarried(y, S)).toBe(true);
    expect(levelOdds(u1, t, plan)).toEqual({ value: null, note: null, carried: true });
    expect(levelOdds(am, t, plan).value).toBe(58.1);
    expect(ownOdds(u1, plan)).toBe(56);
    expect(ownOdds(y, plan)).toBeNull();
  });

  it('records which sessions missed a level', () => {
    const t = plan.last!.t;
    expect(levelTrack(plan.levels[1], t, plan).map((s) => `${s.name}:${s.state}`)).toEqual(['Asia:miss', 'London:miss', 'NY AM:hit']);
    expect(levelTrack(plan.levels[0], t, plan).map((s) => s.state)).toEqual(['miss', 'miss', 'live']);
  });

  it('builds the board', () => {
    const b = buildBoard(plan, plan.last!.t, 7500);
    expect(b.move).toBe(-200);
    expect(b.dayType).toEqual({ label: 'Trend day ↓', tone: 'trend' });
    expect(b.adrMultiple).toBe(2.2);
    expect(b.above.map((r) => r.level.id)).toEqual(['y_ibx', 'asia_u1']);
    expect(b.below.map((r) => r.level.id)).toEqual(['am_d0.5']);
    expect(b.done.map((r) => r.level.id)).toEqual(['asia_d1']);
    expect(b.watch).toContain('NY AM -0.5 SD');
    expect(b.tally.map((s) => [s.name, s.hit, s.missed])).toEqual([['Asia', 0, 3], ['London', 0, 3], ['NY AM', 1, 0]]);
  });

  it('puts the panel\'s nearby targets and today\'s hits on the chart, not session opens', () => {
    expect(chartLevels(plan, plan.last!.t, 7500).map((l) => l.id).sort()).toEqual(['am_d0.5', 'asia_d1', 'asia_u1', 'y_ibx']);
  });
});

describe('hour stats on the board', () => {
  it('lists the live hour prior-hour high as a target and keeps only this hour in done', () => {
    const t = S + 17 * H;
    const hh = lv({ id: 'hh_1', label: '8 AM prior-hour high', price: 7505, frm: S + 17 * H, origUntil: S + 18 * H, until: S + 18 * H, hour: true, odds: 54.4 });
    const oldHit = lv({ id: 'hl_0', label: '7 AM prior-hour low', price: 7495, frm: S + 16 * H, origUntil: S + 17 * H, until: S + 17 * H, hour: true, hitAt: S + 16.5 * H });
    const board = buildBoard({ ...plan, levels: [...plan.levels, hh, oldHit] }, t, 7500);
    expect(board.above.map((r) => r.level.id)).toContain('hh_1');
    expect(board.done.map((r) => r.level.id)).not.toContain('hl_0');
    expect(board.tally.every((x) => x.hit + x.missed < 10)).toBe(true);
  });
});
