/**
 * Money per price step for any symbol, so risk tools can show points, ticks and dollars.
 *
 * Order of trust: the trader's own override, then MT5 (tick size / tick value from the
 * broker), then a built-in table of common futures, then a guess from the chart's
 * minimum move at $1 per point.
 */
export interface ContractSpec {
  /** Smallest price step. */
  tickSize: number;
  /** Money one tick is worth for one contract / lot. */
  tickValue: number;
  currency: string;
  source: 'custom' | 'mt5' | 'table' | 'guess';
}

export interface BrokerSymbolSpec {
  tick_size?: number | null;
  tick_value?: number | null;
  currency?: string | null;
}

// root symbol: [tick size, tick value in USD]
const FUTURES: Record<string, [number, number]> = {
  ES: [0.25, 12.5], MES: [0.25, 1.25],
  NQ: [0.25, 5], MNQ: [0.25, 0.5],
  YM: [1, 5], MYM: [1, 0.5],
  RTY: [0.1, 5], M2K: [0.1, 0.5],
  CL: [0.01, 10], MCL: [0.01, 1], QM: [0.025, 12.5],
  NG: [0.001, 10], QG: [0.005, 12.5],
  GC: [0.1, 10], MGC: [0.1, 1],
  SI: [0.005, 25], SIL: [0.005, 5],
  HG: [0.0005, 12.5], MHG: [0.0005, 1.25],
  ZB: [1 / 32, 31.25], ZN: [1 / 64, 15.625], ZF: [1 / 128, 7.8125], ZT: [1 / 256, 7.8125],
  '6E': [0.00005, 6.25], M6E: [0.0001, 1.25],
  '6B': [0.0001, 6.25], '6J': [0.0000005, 6.25], '6A': [0.00005, 5], '6C': [0.00005, 5],
  ZC: [0.25, 12.5], ZS: [0.25, 12.5], ZW: [0.25, 12.5],
  BTC: [5, 25], MBT: [5, 0.5], ETH: [0.5, 25], MET: [0.5, 0.05],
};

// MT5 / broker spellings of the same contracts.
const ALIASES: Record<string, string> = { EP: 'ES', ENQ: 'NQ', YM: 'YM', DJ: 'YM', CLE: 'CL', GCE: 'GC' };

const MONTH_CODE = /^([A-Z0-9]{1,4}?)([FGHJKMNQUVXZ])(\d{1,4})$/;

/** "ESZ6", "@EP", "/NQ", "ES 12-26" -> "ES" / "NQ". */
export function rootSymbol(symbol: string): string {
  let s = symbol.toUpperCase().trim().replace(/^[@/]+/, '').split(/[\s.:_-]/)[0] ?? '';
  if (FUTURES[s] || ALIASES[s]) return ALIASES[s] ?? s;
  const m = MONTH_CODE.exec(s);
  if (m && (FUTURES[m[1]] || ALIASES[m[1]])) s = m[1];
  return ALIASES[s] ?? s;
}

export function tableSpec(symbol: string): ContractSpec | null {
  const row = FUTURES[rootSymbol(symbol)];
  return row ? { tickSize: row[0], tickValue: row[1], currency: 'USD', source: 'table' } : null;
}

export function resolveContractSpec(input: {
  symbol: string | null;
  minMove: number | null;
  broker?: BrokerSymbolSpec | null;
  customPointValue?: number | null;
}): ContractSpec {
  const fromTable = input.symbol ? tableSpec(input.symbol) : null;
  const b = input.broker;
  const fromBroker: ContractSpec | null =
    b && b.tick_size && b.tick_size > 0 && b.tick_value && b.tick_value > 0
      ? { tickSize: b.tick_size, tickValue: b.tick_value, currency: b.currency || 'USD', source: 'mt5' }
      : null;
  const base: ContractSpec = fromBroker ?? fromTable ?? {
    tickSize: input.minMove && input.minMove > 0 ? input.minMove : 0.01,
    tickValue: input.minMove && input.minMove > 0 ? input.minMove : 0.01,
    currency: 'USD',
    source: 'guess',
  };
  if (input.customPointValue && input.customPointValue > 0) {
    return { ...base, tickValue: input.customPointValue * base.tickSize, source: 'custom' };
  }
  return base;
}

export function pointValue(spec: ContractSpec): number {
  return spec.tickValue / spec.tickSize;
}

/** Decimal places that show every tick (0.25 -> 2, 1/32 -> 5). */
export function priceDecimals(tickSize: number): number {
  for (let d = 0; d <= 8; d += 1) {
    if (Math.abs(Math.round(tickSize * 10 ** d) - tickSize * 10 ** d) < 1e-9) return d;
  }
  return 8;
}
