import { pointValue, priceDecimals, type ContractSpec } from './contractSpecs';

export type PositionSide = 'long' | 'short';
export type PositionHandle = 'entry' | 'stop' | 'target';

/** A risk-to-reward plan drawn on the chart. Prices are snapped to the tick size. */
export interface PositionToolState {
  side: PositionSide;
  /** Epoch seconds of the bar where the plan starts (left edge of the drawing). */
  time: number;
  entry: number;
  stop: number;
  target: number;
  qty: number;
}

export interface PositionLine {
  key: PositionHandle | 'ladder';
  price: number;
  color: string;
  dashed: boolean;
  label: string;
}

export interface PositionLeg {
  points: number;
  ticks: number;
  money: number;
}

export interface PositionModel {
  valid: boolean;
  risk: PositionLeg;
  reward: PositionLeg;
  /** Reward divided by risk. */
  rr: number;
  lines: PositionLine[];
  decimals: number;
  pointValue: number;
}

export const POSITION_COLORS = {
  entry: '#E9C46A',
  stop: '#E0574A',
  target: '#3FB950',
  ladder: 'rgba(63, 185, 80, 0.75)',
} as const;

const LADDER_STEPS = [0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const DEFAULT_STOP_TICKS = 16;
const SWING_BARS = 20;

export function snapToTick(price: number, tickSize: number): number {
  const steps = Math.round(price / tickSize);
  return Number((steps * tickSize).toFixed(priceDecimals(tickSize)));
}

export function formatMoney(value: number, currency = 'USD'): string {
  const sign = value < 0 ? '-' : '';
  const symbol = currency === 'USD' ? '$' : `${currency} `;
  return `${sign}${symbol}${Math.abs(value).toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: Math.abs(value) < 1000 && !Number.isInteger(Math.abs(value)) ? 2 : 0 })}`;
}

/**
 * A new plan at the clicked price: the stop goes just past the recent swing (the lowest
 * low of the last bars for a long, highest high for a short) when that is on the right
 * side of the entry, otherwise a fixed number of ticks away; the target is 2R.
 */
export function createPosition(
  side: PositionSide,
  entryPrice: number,
  time: number,
  recentBars: readonly { high: number; low: number }[],
  tickSize: number,
): PositionToolState {
  const entry = snapToTick(entryPrice, tickSize);
  const bars = recentBars.slice(-SWING_BARS);
  let stop: number;
  if (side === 'long') {
    const swing = bars.length ? Math.min(...bars.map((b) => b.low)) - tickSize : NaN;
    stop = Number.isFinite(swing) && swing < entry - tickSize ? swing : entry - DEFAULT_STOP_TICKS * tickSize;
  } else {
    const swing = bars.length ? Math.max(...bars.map((b) => b.high)) + tickSize : NaN;
    stop = Number.isFinite(swing) && swing > entry + tickSize ? swing : entry + DEFAULT_STOP_TICKS * tickSize;
  }
  stop = snapToTick(stop, tickSize);
  const target = snapToTick(entry + 2 * (entry - stop), tickSize);
  return { side, time, entry, stop, target, qty: 1 };
}

/** Lines, labels and money for a plan. */
export function buildPositionModel(state: PositionToolState, spec: ContractSpec): PositionModel {
  const decimals = priceDecimals(spec.tickSize);
  const pv = pointValue(spec);
  const dir = state.side === 'long' ? 1 : -1;
  const riskPts = dir * (state.entry - state.stop);
  const rewardPts = dir * (state.target - state.entry);
  const valid = riskPts > 0 && rewardPts > 0;
  const leg = (pts: number): PositionLeg => ({
    points: Math.abs(pts),
    ticks: Math.round(Math.abs(pts) / spec.tickSize),
    money: Math.abs(pts) * pv * state.qty,
  });
  const risk = leg(riskPts);
  const reward = leg(rewardPts);
  const rr = valid ? rewardPts / riskPts : 0;
  const p = (v: number): string => v.toFixed(decimals);
  const pts = (v: number): string => v.toFixed(decimals);
  const pct = (v: number): string => `${((v / state.entry) * 100).toFixed(2)}%`;
  const lines: PositionLine[] = [
    {
      key: 'stop', price: state.stop, color: POSITION_COLORS.stop, dashed: false,
      label: `Stop ${p(state.stop)} · ${pts(risk.points)} pts (${pct(risk.points)}) · ${risk.ticks} ticks · ${formatMoney(-risk.money, spec.currency)}`,
    },
    {
      key: 'entry', price: state.entry, color: POSITION_COLORS.entry, dashed: false,
      label: `${state.side === 'long' ? 'Long' : 'Short'} ${state.qty} @ ${p(state.entry)}`,
    },
    {
      key: 'target', price: state.target, color: POSITION_COLORS.target, dashed: false,
      label: `Target ${p(state.target)} · ${pts(reward.points)} pts · ${reward.ticks} ticks · ${formatMoney(reward.money, spec.currency)} · ${rr.toFixed(2)}R`,
    },
  ];
  if (valid) {
    for (const r of LADDER_STEPS) {
      if (r >= rr - 1e-9) break;
      lines.push({
        key: 'ladder', price: state.entry + dir * r * riskPts, color: POSITION_COLORS.ladder, dashed: true,
        label: `${r}R ${formatMoney(r * risk.money, spec.currency)}`,
      });
    }
  }
  return { valid, risk, reward, rr, lines, decimals, pointValue: pv };
}

/** Move one handle to a price (snapped). The other two stay put. */
export function moveHandle(state: PositionToolState, handle: PositionHandle, price: number, tickSize: number): PositionToolState {
  return { ...state, [handle]: snapToTick(price, tickSize) };
}

/** Swap long/short, mirroring the stop and target around the entry. */
export function flipSide(state: PositionToolState, tickSize: number): PositionToolState {
  return {
    ...state,
    side: state.side === 'long' ? 'short' : 'long',
    stop: snapToTick(2 * state.entry - state.stop, tickSize),
    target: snapToTick(2 * state.entry - state.target, tickSize),
  };
}
