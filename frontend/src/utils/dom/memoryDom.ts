/**
 * Memory DOM: turns dom-service's state into ladder rows (NinjaTrader SuperDOM columns plus
 * what the big orders at each price did and how price reacted).
 */
export type DomSide = 'b' | 'a';
export type DomKind = 'pulled' | 'filled' | 'held';

export interface DomEvent {
  id: number;
  kind: DomKind;
  side: DomSide;
  price: number;
  t: number;
  peak: number;
  size: number;
  filled: number;
  pulled: number;
  absorbed: number;
  tests: number;
  dist_ticks: number;
  ref: number;
  away: number;
  through: number;
  m1: number | null;
  m5: number | null;
  done: boolean | number;
}

export interface DomStat { kind: DomKind; side: DomSide; n: number; awayPct: number; m5: number; away: number; through: number; days: number }

export interface DomState {
  sym: string;
  tick: number;
  last: number | null;
  lastT: number;
  bid: number | null;
  ask: number | null;
  bids: [number, number][];
  asks: [number, number][];
  /** [price, sold, bought] this trading day */
  vol: [number, number, number][];
  /** live big orders: [side, price, size, peak, holds, absorbed] */
  big: [DomSide, number, number, number, number, number][];
  memory: [number, DomEvent[]][];
  stats: DomStat[];
  connected: boolean;
  day: string;
}

export interface LadderRow {
  price: number;
  key: number;
  bid: number | null;
  ask: number | null;
  sold: number | null;
  bought: number | null;
  /** live big order resting here */
  big: { side: DomSide; size: number; peak: number; holds: number } | null;
  isLast: boolean;
  events: DomEvent[];
  badge: { kind: DomKind; text: string } | null;
  note: string | null;
}

const PT = 'America/Los_Angeles';
export const timePt = (ms: number): string =>
  new Date(ms).toLocaleTimeString('en-US', { timeZone: PT, hour: 'numeric', minute: '2-digit' });
const pts = (v: number): string => (Math.round(Math.abs(v) * 4) / 4).toLocaleString('en-US', { maximumFractionDigits: 2 });
const n0 = (v: number): string => v.toLocaleString('en-US');
export const fmtPrice = (p: number): string => p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "price fell 5.25 in 5 min" / "so far up 2" for one event, from the level's point of view. */
export function reaction(ev: DomEvent): string {
  const up = ev.side === 'b' ? 1 : -1; // positive numbers are away from the level
  const done = Boolean(ev.done) && ev.m5 !== null;
  const move = done ? ev.m5! : ev.away >= ev.through ? ev.away : -ev.through;
  const real = move * up; // actual price direction
  if (Math.abs(real) < 0.125) return done ? 'price flat after 5 min' : 'watching price…';
  const verb = real > 0 ? 'rose' : 'fell';
  return done ? `price ${verb} ${pts(real)} in 5 min` : `so far price ${verb} ${pts(real)}`;
}

/** One line for an event, plain words. */
export function eventText(ev: DomEvent): string {
  const what = ev.side === 'b' ? 'bid' : 'offer';
  const at = timePt(ev.t);
  if (ev.kind === 'pulled') {
    const near = ev.dist_ticks === 0 ? ' with price right at it' : ev.dist_ticks <= 4 ? ` with price ${ev.dist_ticks} tick${ev.dist_ticks === 1 ? '' : 's'} away` : '';
    return `${n0(ev.peak)} ${what} pulled ${at}${near}; ${reaction(ev)}`;
  }
  if (ev.kind === 'filled') {
    const hit = ev.side === 'b' ? 'sold into it' : 'bought into it';
    return `${n0(ev.filled)} ${hit}, gone ${at}; ${reaction(ev)}`;
  }
  const hit = ev.side === 'b' ? 'sold' : 'bought';
  return `Held ${at} (${n0(ev.absorbed)} ${hit} into it); ${reaction(ev)}`;
}

/** The short version for the ladder cell: "600 pulled 5:02 · ▼6.25 in 5m". */
export function shortText(ev: DomEvent): string {
  const at = timePt(ev.t).replace(/ [AP]M$/, '');
  const up = ev.side === 'b' ? 1 : -1;
  const done = Boolean(ev.done) && ev.m5 !== null;
  const real = (done ? ev.m5! : ev.away >= ev.through ? ev.away : -ev.through) * up;
  const move = Math.abs(real) < 0.125 ? (done ? 'flat in 5m' : 'watching') : `${real > 0 ? '▲' : '▼'}${pts(real)}${done ? ' in 5m' : ' so far'}`;
  const what = ev.kind === 'pulled' ? `${n0(ev.peak)} pulled` : ev.kind === 'filled' ? `${n0(ev.filled)} eaten` : `held ${n0(ev.absorbed)}`;
  return `${what} ${at} · ${move}`;
}

function badge(events: DomEvent[]): LadderRow['badge'] {
  if (!events.length) return null;
  const last = events[events.length - 1];
  const count = events.filter((e) => e.kind === last.kind).length;
  return { kind: last.kind, text: count > 1 ? `${last.kind} ${count}x` : last.kind };
}

/** The ladder's rows from `top` down `count` ticks. */
export function buildLadder(s: DomState, top: number, count: number): LadderRow[] {
  const tick = s.tick || 0.25;
  const k = (p: number): number => Math.round(p / tick);
  const bids = new Map(s.bids.map(([p, v]) => [k(p), v]));
  const asks = new Map(s.asks.map(([p, v]) => [k(p), v]));
  const vol = new Map(s.vol.map(([p, sold, bought]) => [k(p), [sold, bought] as const]));
  const big = new Map(s.big.map(([side, p, size, peak, holds]) => [k(p), { side, size, peak, holds }]));
  const mem = new Map(s.memory.map(([p, evs]) => [k(p), evs]));
  const lastK = s.last !== null ? k(s.last) : null;
  const rows: LadderRow[] = [];
  const topK = k(top);
  for (let i = 0; i < count; i++) {
    const key = topK - i;
    const events = mem.get(key) ?? [];
    const v = vol.get(key);
    rows.push({
      price: Math.round(key * tick * 100) / 100,
      key,
      bid: bids.get(key) ?? null,
      ask: asks.get(key) ?? null,
      sold: v && v[0] ? v[0] : null,
      bought: v && v[1] ? v[1] : null,
      big: big.get(key) ?? null,
      isLast: key === lastK,
      events,
      badge: badge(events),
      note: events.length ? shortText(events[events.length - 1]) : null,
    });
  }
  return rows;
}

/** The memory's lessons so far, one sentence each (bids first). */
export function statLines(stats: DomStat[]): { text: string; n: number }[] {
  const order: Record<string, number> = { 'pulled-b': 0, 'pulled-a': 1, 'filled-b': 2, 'filled-a': 3, 'held-b': 4, 'held-a': 5 };
  return [...stats]
    .sort((x, y) => (order[`${x.kind}-${x.side}`] ?? 9) - (order[`${y.kind}-${y.side}`] ?? 9))
    .map((st) => {
      const what = st.side === 'b' ? 'bids' : 'offers';
      const dir = st.side === 'b' ? 'higher' : 'lower';
      const name = st.kind === 'pulled' ? `Big ${what} pulled` : st.kind === 'filled' ? `Big ${what} eaten` : `Big ${what} that held`;
      return { text: `${name}: price ${dir} 5 min later ${st.awayPct}% of the time`, n: st.n };
    });
}
