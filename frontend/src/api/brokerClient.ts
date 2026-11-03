import type { BrokerSymbolSpec } from '@/utils/chart/contractSpecs';

const BROKER_BASE_URL = '/api/broker';

/** Tick size / tick value for a symbol from the MT5 bridge, or null when it isn't reachable. */
export async function fetchBrokerSymbolSpec(symbol: string): Promise<BrokerSymbolSpec | null> {
  try {
    const response = await fetch(`${BROKER_BASE_URL}/symbols/${encodeURIComponent(symbol)}`);
    if (!response.ok) return null;
    const body = (await response.json()) as Record<string, unknown>;
    const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null);
    return {
      tick_size: num(body.tick_size),
      tick_value: num(body.tick_value),
      currency: typeof body.currency === 'string' ? body.currency : null,
    };
  } catch {
    return null;
  }
}
