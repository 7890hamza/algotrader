/**
 * Game Plan: turns the indicator API's day plan into what the panel and the chart show at one
 * moment: which targets are open, done or carried, and which sessions missed which ones.
 */
export type SessionKey = 'asia' | 'ldn' | 'am' | 'pm';
export const SESSION_KEYS: readonly SessionKey[] = ['asia', 'ldn', 'am', 'pm'];
export const SESSION_NAMES: Record<SessionKey, string> = { asia: 'Asia', ldn: 'London', am: 'NY AM', pm: 'NY PM' };

export interface PlanLevel {
  id: string;
  group: string;
  label: string;
  price: number;
  /** Epoch ms: when the level wakes up, its own window ends (odds stop applying), it leaves the board. */
  frm: number;
  origUntil: number;
  until: number;
  oddsFrom?: number | null;
  odds: number | null;
  kind: 'target' | 'open' | 'hour_open';
  hour?: boolean;
  hitAt: number | null;
  never: boolean;
  side?: 'up' | 'dn';
  why?: string | null;
  color: string;
  fromDay?: string;
  prevMissed?: string[];
  sweep?: { id: string; at: number };
}

export interface DayPlan {
  symbol: string;
  key: string;
  label: string;
  start: number;
  end: number;
  sessions: Record<SessionKey, [number, number]>;
  levels: PlanLevel[];
  last: { t: number; close: number } | null;
  /** The day's price per 5 minutes: [bucket start ms, high, low, close]. */
  path?: number[][];
  ctx: {
    rth0: number;
    ib1: number;
    rth1: number;
    adr: number | null;
    setupEth?: string;
    setupRth?: string;
    ib?: { high: number; low: number; mid: number; side: number };
    dayOpen?: number;
    dayHigh?: number;
    dayLow?: number;
    rthOpen?: number;
    rthHigh?: number;
    rthLow?: number;
    ethOver: { other_held: number; one_by_close: number };
    /** ALN pattern at 5 AM: 1-4 and what London did with Asia's range. */
    aln?: { pattern: number; text: string };
  };
}

export type LevelStatus = 'later' | 'open' | 'done' | 'expired';
export type TrackState = 'hit' | 'miss' | 'live';
export interface TrackStep { key: SessionKey; name: string; state: TrackState }

const MINUTE = 60_000;

export function levelStatus(l: PlanLevel, t: number): LevelStatus {
  if (l.never || l.frm > t) return 'later';
  if (l.hitAt !== null && l.hitAt <= t) return 'done';
  if (t + MINUTE >= l.until) return 'expired';
  return 'open';
}

/** Past its own window (its odds no longer apply) or brought in from the day before. */
export function isCarried(l: PlanLevel, t: number): boolean {
  return Boolean(l.fromDay) || t >= l.origUntil;
}

/** Each session that had a shot at the level and how it did. */
export function levelTrack(l: PlanLevel, t: number, plan: DayPlan): TrackStep[] {
  if (l.never) return [];
  const end = l.hitAt ?? l.until;
  const out: TrackStep[] = [];
  for (const key of SESSION_KEYS) {
    const [a, b] = plan.sessions[key];
    if (b <= l.frm || a >= end || a > t) continue;
    let state: TrackState = 'live';
    if (l.hitAt !== null && l.hitAt >= a && l.hitAt < b && l.hitAt <= t) state = 'hit';
    else if (b <= t + MINUTE) state = 'miss';
    out.push({ key, name: SESSION_NAMES[key], state });
  }
  return out;
}

export interface Odds { value: number | null; note: string | null; carried: boolean }

export function levelOdds(l: PlanLevel, t: number, plan: DayPlan): Odds {
  if (isCarried(l, t)) return { value: null, note: null, carried: true };
  if (l.oddsFrom && t < l.oddsFrom) return { value: null, note: 'odds post at 6:30 AM', carried: false };
  if (l.group === 'pETH' && t >= plan.ctx.rth0) {
    const other = plan.levels.find((x) => x.group === 'pETH' && x.id !== l.id && !x.fromDay);
    if (other && other.hitAt !== null && other.hitAt < plan.ctx.rth0) {
      const held = plan.ctx.ethOver.other_held;
      return { value: Math.round((100 - held) * 10) / 10, note: `the other side went overnight; this side holds ${held}% of the time`, carried: false };
    }
  }
  return { value: l.odds, note: null, carried: false };
}

/** The odds a level had in its own window (for the done list and the session tally). */
export function ownOdds(l: PlanLevel, plan: DayPlan): number | null {
  if (l.fromDay) return null;
  return levelOdds(l, Math.max(l.frm, l.oddsFrom ?? 0), plan).value;
}

export interface BoardRow { level: PlanLevel; odds: Odds; distance: number; track: TrackStep[] }
export interface SessionTally { key: SessionKey; name: string; hit: number; missed: number; live: boolean }
export interface Board {
  dayType: { label: string; tone: 'range' | 'either' | 'trend' } | null;
  move: number | null;
  rangeSoFar: number | null;
  adrMultiple: number | null;
  watch: string;
  above: BoardRow[];
  below: BoardRow[];
  done: BoardRow[];
  /** Every open target, highest first (the panel's "all open" list). */
  allOpen: BoardRow[];
  tally: SessionTally[];
}

const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPts = (v: number): string => (Math.round(Math.abs(v) * 4) / 4).toLocaleString('en-US', { maximumFractionDigits: 2 });

function isBoardTarget(l: PlanLevel): boolean {
  return l.kind === 'target' && !l.hour;
}

/** Everything the panel shows at time `t` with the last price `price`. */
export function buildBoard(plan: DayPlan, t: number, price: number, opts: { rows?: number } = {}): Board {
  const rows = opts.rows ?? 3;
  const { ctx } = plan;
  const row = (l: PlanLevel): BoardRow => ({ level: l, odds: levelOdds(l, t, plan), distance: l.price - price, track: levelTrack(l, t, plan) });

  // prior-hour highs / lows count as targets while their hour is live
  const open = plan.levels.filter((l) => (isBoardTarget(l) || l.kind === 'hour_open' || (l.kind === 'target' && l.hour)) && levelStatus(l, t) === 'open');
  const above = open.filter((l) => l.price > price).sort((a, b) => a.price - b.price).slice(0, rows).map(row).reverse();
  const below = open.filter((l) => l.price <= price).sort((a, b) => b.price - a.price).slice(0, rows).map(row);
  const done = plan.levels
    .filter((l) => (isBoardTarget(l) || (l.kind === 'target' && l.hour && l.until > t)) && levelStatus(l, t) === 'done')
    .sort((a, b) => (b.hitAt ?? 0) - (a.hitAt ?? 0))
    .map(row);
  const allOpen = open.filter((l) => l.kind === 'target').sort((a, b) => b.price - a.price).map(row);

  // Day type from the RTH range so far: under 40 range-day size, 40-60 either way, over 60 trend.
  let dayType: Board['dayType'] = null;
  const hi = Math.max(ctx.rthHigh ?? -Infinity, t >= ctx.rth0 && t < ctx.rth1 ? price : -Infinity);
  const lo = Math.min(ctx.rthLow ?? Infinity, t >= ctx.rth0 && t < ctx.rth1 ? price : Infinity);
  if (Number.isFinite(hi) && Number.isFinite(lo) && ctx.rthOpen !== undefined) {
    const r = hi - lo;
    const down = price < ctx.rthOpen;
    if (r < 40) dayType = { label: 'Range day', tone: 'range' };
    else if (r <= 60) dayType = { label: 'Could go either way', tone: 'either' };
    else dayType = { label: `Trend day ${down ? '↓' : '↑'}`, tone: 'trend' };
  }
  const move = ctx.dayOpen !== undefined ? price - ctx.dayOpen : null;
  const dayHi = Math.max(ctx.dayHigh ?? price, price);
  const dayLo = Math.min(ctx.dayLow ?? price, price);
  const rangeSoFar = ctx.dayOpen !== undefined ? dayHi - dayLo : null;
  const adrMultiple = rangeSoFar !== null && ctx.adr ? Math.round((rangeSoFar / ctx.adr) * 10) / 10 : null;

  // Session tally: targets each finished session hit vs. left behind.
  const tally: SessionTally[] = [];
  for (const key of SESSION_KEYS) {
    const [a] = plan.sessions[key];
    if (a > t) continue;
    let hit = 0;
    let missed = 0;
    let live = false;
    for (const l of plan.levels) {
      if (!isBoardTarget(l)) continue;
      const step = levelTrack(l, t, plan).find((s) => s.key === key);
      if (!step) continue;
      if (step.state === 'hit') hit++;
      else if (step.state === 'miss') missed++;
      else live = true;
    }
    const [, b] = plan.sessions[key];
    tally.push({ key, name: SESSION_NAMES[key], hit, missed, live: live || b > t + MINUTE });
  }

  return { dayType, move, rangeSoFar, adrMultiple, watch: watchLine(plan, t, price, above, below), above, below, done, allOpen, tally };
}

/** One plain sentence: the strongest nearby open target, or what is about to matter. */
function watchLine(plan: DayPlan, t: number, price: number, above: BoardRow[], below: BoardRow[]): string {
  const { ctx } = plan;
  if (t >= ctx.rth0 && t < ctx.ib1) return 'The IB (first hour of RTH) is still forming. At 7:30 the IB high and low post with their break odds.';
  const sweep = plan.levels.find((l) => l.kind === 'hour_open' && levelStatus(l, t) === 'open' && l.sweep);
  if (sweep && sweep.odds !== null) {
    return `This hour swept its prior-hour ${sweep.sweep!.id.startsWith('hh') ? 'high' : 'low'}. It comes back to the hour open (${fmt(sweep.price)}) ${sweep.odds}% of the time.`;
  }
  const withOdds = [...above, ...below].filter((r) => r.odds.value !== null && r.level.kind === 'target');
  const best = withOdds.sort((a, b) => Math.abs(a.distance) - Math.abs(b.distance))[0];
  if (best) {
    const dir = best.distance > 0 ? 'above' : 'below';
    const v = best.odds.value!;
    const plain = v >= 70 ? `Most days get there (${v}%)` : v >= 40 ? `About ${Math.round(v)}% of days get there` : v === 25 ? 'Only 1 in 4 days get that far' : `Only ${Math.round(v)}% of days get that far`;
    return `Next stat ${dir} is the ${best.level.label} at ${fmt(best.level.price)}, ${fmtPts(best.distance)} pts away. ${plain}.`;
  }
  const carried = [...above, ...below].find((r) => r.odds.carried);
  if (carried) {
    const missed = carried.track.filter((s) => s.state === 'miss').map((s) => s.name);
    const who = carried.level.fromDay ? `all of ${carried.level.fromDay}` : missed.join(' and ') || 'its session';
    return `Nearest is ${carried.level.label} at ${fmt(carried.level.price)}, carried over: ${who} missed it.`;
  }
  return t < plan.start ? 'The session has not started.' : 'No open targets near price.';
}
