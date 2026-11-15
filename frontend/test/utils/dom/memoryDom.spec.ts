import { describe, expect, it } from 'vitest';

import { buildLadder, eventText, reaction, shortText, statLines, type DomEvent, type DomState } from '@/utils/dom/memoryDom';

const T = Date.UTC(2026, 10, 9, 17, 41); // 9:41 AM PT

function ev(p: Partial<DomEvent>): DomEvent {
  return {
    id: 1, kind: 'pulled', side: 'b', price: 7442.25, t: T, peak: 620, size: 0, filled: 0, pulled: 620,
    absorbed: 0, tests: 0, dist_ticks: 2, ref: 7443, away: 1, through: 5.25, m1: -2, m5: -5.25, done: 1, ...p,
  };
}

const state: DomState = {
  sym: 'ES 12-26', tick: 0.25, last: 7443.5, lastT: T, bid: 7443.25, ask: 7443.5,
  bids: [[7443.25, 27], [7442.25, 701]],
  asks: [[7443.5, 40], [7444.25, 487]],
  vol: [[7443.25, 24, 0], [7443.5, 18, 40]],
  big: [['b', 7442.25, 701, 701, 2, 380]],
  memory: [[7442.25, [ev({ kind: 'held', absorbed: 380, away: 6, through: 0.5, m5: 6 }), ev({ kind: 'held', absorbed: 120, m5: 2 })]], [7445, [ev({ side: 'a', price: 7445, m5: -3.5 })]]],
  stats: [{ kind: 'pulled', side: 'b', n: 12, awayPct: 25, m5: -3, away: 2, through: 5, days: 3 }, { kind: 'held', side: 'a', n: 4, awayPct: 75, m5: 2, away: 4, through: 1, days: 2 }],
  connected: true,
  day: '2026-11-09',
};

describe('memory DOM ladder', () => {
  it('lines up book, volume, big orders and memory by price', () => {
    const rows = buildLadder(state, 7445, 12);
    expect(rows[0].price).toBe(7445);
    expect(rows.at(-1)!.price).toBe(7442.25);
    const last = rows.find((r) => r.isLast)!;
    expect(last.price).toBe(7443.5);
    expect([last.ask, last.sold, last.bought]).toEqual([40, 18, 40]);
    const wall = rows.find((r) => r.price === 7442.25)!;
    expect(wall.bid).toBe(701);
    expect(wall.big?.holds).toBe(2);
    expect(wall.badge).toEqual({ kind: 'held', text: 'held 2x' });
    expect(rows[0].badge?.text).toBe('pulled');
  });

  it('says what happened in plain words', () => {
    expect(eventText(ev({}))).toBe('620 bid pulled 9:41 AM with price 2 ticks away; price fell 5.25 in 5 min');
    expect(eventText(ev({ side: 'a', m5: -3.5 }))).toContain('offer pulled');
    expect(reaction(ev({ side: 'a', m5: -3.5 }))).toBe('price rose 3.5 in 5 min');
    expect(eventText(ev({ kind: 'filled', filled: 540 }))).toMatch(/^540 sold into it, gone 9:41 AM/);
    expect(reaction(ev({ done: 0, m5: null, away: 2, through: 0 }))).toBe('so far price rose 2');
    expect(eventText(ev({ dist_ticks: 0 }))).toContain('with price right at it');
    expect(shortText(ev({}))).toBe('620 pulled 9:41 · ▼5.25 in 5m');
    expect(shortText(ev({ kind: 'held', absorbed: 380, m5: 6 }))).toBe('held 380 9:41 · ▲6 in 5m');
  });

  it('turns the stats into lessons, bids first', () => {
    const lines = statLines(state.stats);
    expect(lines[0]).toEqual({ text: 'Big bids pulled: price higher 5 min later 25% of the time', n: 12 });
    expect(lines[1].text).toBe('Big offers that held: price lower 5 min later 75% of the time');
  });
});
