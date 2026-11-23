/**
 * Daily candle: how Austin and Riley (the Algo Wizard) each read one CME day. No trades - just the
 * levels and boxes each one marks, the call each one would make at the New York open, and (once the
 * day is over) whether price went their way.
 *
 * Every time below is "minutes since 6 PM New York" (the CME day start), called dm.
 *   dm   0 = 6 PM NY  = 3 PM PT          dm 720 = 6 AM NY = 3 AM PT
 *   dm 360 = midnight = 9 PM PT          dm 930 = 9:30 AM = 6:30 AM PT
 *   dm 1320 = 4 PM NY = 1 PM PT (the day's "close" for these reads)
 */

export interface DcBar { t: number; o: number; h: number; l: number; c: number }

/** Austin's 4 stat windows (dm): 3-4 PM, 12-1 AM, 6:30-7:30 AM, 12-1 PM Pacific. */
export const STAT_WINDOWS: readonly [number, number][] = [[0, 60], [540, 600], [930, 990], [1260, 1320]];
export const inStat = (dm: number): boolean => STAT_WINDOWS.some(([a, b]) => dm >= a && dm < b);
/** Riley's measured runs past a broken box edge, as a share of the box height. */
export const P_LINES: readonly [string, number][] = [['P30', 0.24], ['P50', 0.47], ['P70', 0.98]];

const DAY_END = 1320;
const BREAK_LAST = 1080; // Riley stops looking for the first break at noon NY (9 AM PT)

export interface Range { hi: number; lo: number }
export interface Extreme { price: number; t: number; dm: number; inStat: boolean }
export type Verdict = 'right' | 'wrong' | 'no-call' | 'pending';

export interface AustinRead {
  p12: Range | null; // 3 PM - 3 AM PT
  midnightOpen: number | null; // 9 PM PT
  q1: Range | null; // 3:00 - 5:30 AM PT
  /** at 6:30 AM PT: the high and low so far, and whether each formed in a stat window */
  high: Extreme | null;
  low: Extreme | null;
  lean: 1 | -1 | 0 | null; // null = 6:30 not reached yet
  priceAtOpen: number | null;
  verdict: Verdict;
  why: string;
}

export interface RileyRead {
  asia: 1 | -1 | 0 | null; // 5 - 9 PM PT
  london: 1 | -1 | 0 | null; // 11 PM - 2 AM PT
  night: 'trending' | 'contradicting' | null;
  sixBox: Range | null; // 3 - 4 AM PT
  openBox: Range | null; // 6:30 - 7:00 AM PT
  /** first 5-minute close outside the open box: when (ms, end of that 5 minutes) and which way */
  brk: { t: number; dm: number; dir: 1 | -1; edge: number } | null;
  pLines: { name: string; price: number; hit: boolean }[];
  call: 'with' | 'fade' | null; // trending night: go with the break; contradicting: fade it
  held: boolean | null; // at the close: still past the broken edge (True) or back inside (False)
  verdict: Verdict;
  why: string;
}

export interface DayRead {
  day: string; // the NY date the day ends on, YYYY-MM-DD
  start: number; // ms of 6 PM NY
  done: boolean; // reached 1 PM PT
  austin: AustinRead;
  riley: RileyRead;
}

// ---- New York clock -----------------------------------------------------------------------------
const NY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit' });
const offsetCache = new Map<number, number>();
/** New York's offset from UTC in minutes at this moment (cached per hour). */
function nyOffsetMin(ms: number): number {
  const key = Math.floor(ms / 3_600_000);
  let off = offsetCache.get(key);
  if (off === undefined) {
    const p = Object.fromEntries(NY.formatToParts(new Date(key * 3_600_000)).map((x) => [x.type, x.value]));
    const asUtc = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour) % 24);
    off = Math.round((asUtc - key * 3_600_000) / 60_000);
    offsetCache.set(key, off);
  }
  return off;
}
/** The CME day a bar belongs to (NY date it ends on) and its minutes since 6 PM NY. */
export function cmeClock(ms: number): { day: string; dm: number } {
  const nyMs = ms + nyOffsetMin(ms) * 60_000;
  const shifted = new Date(nyMs + 6 * 3_600_000); // 6 PM NY becomes midnight of the next day
  const day = shifted.toISOString().slice(0, 10);
  const dm = shifted.getUTCHours() * 60 + shifted.getUTCMinutes();
  return { day, dm };
}
/** "6:30 AM" in Pacific time from minutes since 6 PM NY. */
export function ptClock(dm: number): string {
  const m = (((dm + 900) % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60); const mm = m % 60;
  return `${h % 12 || 12}${mm ? `:${String(mm).padStart(2, '0')}` : ''} ${h >= 12 ? 'PM' : 'AM'}`;
}

// ---- one day ------------------------------------------------------------------------------------
interface Row extends DcBar { dm: number }

function range(rows: Row[], a: number, b: number): Range | null {
  const s = rows.filter((r) => r.dm >= a && r.dm < b);
  return s.length ? { hi: Math.max(...s.map((r) => r.h)), lo: Math.min(...s.map((r) => r.l)) } : null;
}
function direction(rows: Row[], a: number, b: number, barMin: number): 1 | -1 | 0 | null {
  const s = rows.filter((r) => r.dm >= a && r.dm < b);
  if (!s.length || s[s.length - 1].dm + barMin < b) return null; // not finished yet
  const d = s[s.length - 1].c - s[0].o;
  return d > 0 ? 1 : d < 0 ? -1 : 0;
}

/** Read one CME day from its bars (any timeframe up to 5 minutes; bars after the cursor left out). */
export function readDay(day: string, rows: Row[], barMin: number): DayRead {
  const last = rows[rows.length - 1];
  const done = last.dm + barMin >= DAY_END;
  const close = last.c;
  const start = rows[0].t - rows[0].dm * 60_000;

  // ---- Austin ----
  const p12 = rows.some((r) => r.dm + barMin >= 720) ? range(rows, 0, 720) : null;
  const mo = rows.find((r) => r.dm >= 360 && r.dm < 420);
  const q1 = rows.some((r) => r.dm + barMin >= 870) ? range(rows, 720, 870) : null;
  const atOpen = rows.find((r) => r.dm >= 930);
  const before = rows.filter((r) => r.dm < 930);
  let high: Extreme | null = null; let low: Extreme | null = null; let lean: AustinRead['lean'] = null;
  if (atOpen && before.length) {
    const hb = before.reduce((a, b) => (b.h > a.h ? b : a));
    const lb = before.reduce((a, b) => (b.l < a.l ? b : a));
    high = { price: hb.h, t: hb.t, dm: hb.dm, inStat: inStat(hb.dm) };
    low = { price: lb.l, t: lb.t, dm: lb.dm, inStat: inStat(lb.dm) };
    lean = low.inStat && !high.inStat ? 1 : high.inStat && !low.inStat ? -1 : 0;
  }
  const priceAtOpen = atOpen ? atOpen.o : null;
  let aVerdict: Verdict = 'pending'; let aWhy = 'Waiting for 6:30 AM PT';
  if (lean === 0) { aVerdict = 'no-call'; aWhy = high && low && high.inStat ? 'High and low both in stat: no lean' : 'Neither high nor low in stat: no lean'; }
  else if (lean !== null && done && high && low && priceAtOpen !== null) {
    const after = rows.filter((r) => r.dm >= 930);
    const held = lean > 0 ? Math.min(...after.map((r) => r.l)) >= low.price : Math.max(...after.map((r) => r.h)) <= high.price;
    const moved = (close - priceAtOpen) * lean > 0;
    aVerdict = held && moved ? 'right' : 'wrong';
    const side = lean > 0 ? 'low' : 'high';
    aWhy = held && moved ? `The ${side} held and price ${lean > 0 ? 'rose' : 'fell'} from 6:30 to 1 PM`
      : !held ? `The ${side} he expected to hold got broken` : `The ${side} held, but price ${lean > 0 ? 'didn\'t rise' : 'didn\'t fall'} from 6:30 to 1 PM`;
  } else if (lean !== null) aWhy = lean > 0 ? 'Low in stat: expects the low to hold, looks up' : 'High in stat: expects the high to hold, looks down';

  // ---- Riley ----
  const asia = direction(rows, 120, 360, barMin);
  const london = direction(rows, 480, 660, barMin);
  const night = asia === null || london === null ? null : asia !== 0 && asia === london ? 'trending' : 'contradicting';
  const sixBox = rows.some((r) => r.dm + barMin >= 780) ? range(rows, 720, 780) : null;
  const openBox = rows.some((r) => r.dm + barMin >= 960) ? range(rows, 930, 960) : null;
  let brk: RileyRead['brk'] = null;
  if (openBox) {
    // 5-minute closes from 10:00 NY: the last bar of each 5-minute block
    const blocks = new Map<number, Row>();
    for (const r of rows) if (r.dm >= 960 && r.dm < BREAK_LAST) blocks.set(Math.floor(r.dm / 5), r);
    for (const [blk, r] of [...blocks.entries()].sort((a, b) => a[0] - b[0])) {
      if (r.dm + barMin < blk * 5 + 5) continue; // that 5 minutes isn't finished yet
      if (r.c > openBox.hi || r.c < openBox.lo) {
        const dir = r.c > openBox.hi ? 1 : -1;
        brk = { t: start + (blk * 5 + 5) * 60_000, dm: blk * 5 + 5, dir, edge: dir > 0 ? openBox.hi : openBox.lo };
        break;
      }
    }
  }
  const pLines: RileyRead['pLines'] = [];
  let held: boolean | null = null;
  if (brk && openBox) {
    const size = openBox.hi - openBox.lo;
    const after = rows.filter((r) => r.dm >= brk!.dm);
    const far = brk.dir > 0 ? Math.max(...after.map((r) => r.h), -Infinity) : Math.min(...after.map((r) => r.l), Infinity);
    for (const [name, k] of P_LINES) {
      const price = brk.edge + brk.dir * k * size;
      pLines.push({ name, price, hit: (far - price) * brk.dir >= 0 });
    }
    if (done) held = (close - brk.edge) * brk.dir > 0;
  }
  const call = brk && night ? (night === 'trending' ? 'with' : 'fade') : null;
  let rVerdict: Verdict = 'pending'; let rWhy = 'Waiting for the opening box to break';
  if (done && openBox && !brk) { rVerdict = 'no-call'; rWhy = 'No 5-minute close outside the box before 9 AM PT'; }
  else if (brk && !night) { rVerdict = 'no-call'; rWhy = 'Night type unknown (missing data)'; }
  else if (brk && call && held === null) rWhy = call === 'with' ? 'Trending night: expects the break to hold' : 'Contradicting night: expects the break to fail';
  else if (brk && call && held !== null) {
    const right = (call === 'with') === held;
    rVerdict = right ? 'right' : 'wrong';
    rWhy = `Break ${held ? 'held (True)' : 'failed (False)'}; he ${call === 'with' ? 'expected it to hold' : 'expected it to fail'}`;
  }

  return {
    day, start, done,
    austin: { p12, midnightOpen: mo ? mo.o : null, q1, high, low, lean, priceAtOpen, verdict: aVerdict, why: aWhy },
    riley: { asia, london, night, sixBox, openBox, brk, pLines, call, held, verdict: rVerdict, why: rWhy },
  };
}

/** Read every weekday CME day in the bars (bars after `cursorMs` are ignored). */
export function readDays(bars: readonly DcBar[], barMin: number, cursorMs = Number.POSITIVE_INFINITY): DayRead[] {
  const byDay = new Map<string, Row[]>();
  for (const b of bars) {
    if (b.t > cursorMs) break;
    const { day, dm } = cmeClock(b.t);
    if (dm >= DAY_END) continue; // 4-5 PM NY: after these reads' close
    let rows = byDay.get(day);
    if (!rows) { rows = []; byDay.set(day, rows); }
    rows.push({ ...b, dm });
  }
  const out: DayRead[] = [];
  for (const [day, rows] of byDay) {
    const wd = new Date(`${day}T12:00:00Z`).getUTCDay();
    if (wd === 0 || wd === 6 || rows[0].dm > 30) continue; // weekend, or the day's start isn't loaded
    out.push(readDay(day, rows, barMin));
  }
  return out;
}

/** "Austin 3 of 5 · Riley 2 of 4": finished days where each one made a call. */
export function scoreDays(days: readonly DayRead[]): { austin: { right: number; calls: number }; riley: { right: number; calls: number } } {
  const s = (v: Verdict[]) => ({ right: v.filter((x) => x === 'right').length, calls: v.filter((x) => x === 'right' || x === 'wrong').length });
  return { austin: s(days.map((d) => d.austin.verdict)), riley: s(days.map((d) => d.riley.verdict)) };
}
