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

export interface BrokerOrderRequest {
  symbol: string;
  orderType: 'MARKET' | 'LIMIT' | 'STOP';
  tradeSide: 'BUY' | 'SELL';
  volume: number;
  limitPrice?: number;
  stopPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
  comment?: string;
}

export interface BrokerPosition {
  id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  volume: number;
  price: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  currentPrice: number | null;
  profit: number | null;
}

export interface BrokerOrder {
  id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: string;
  volume: number;
  price: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
}

async function brokerJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BROKER_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === 'string' ? detail : `MT5 bridge error ${response.status}`);
  }
  return body as T;
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v !== 0 ? v : null);

/** Is the bridge up with order sending on (demo account)? */
export async function fetchTradingEnabled(): Promise<boolean> {
  try {
    const accounts = await brokerJson<{ access_rights?: string }[]>('/accounts/');
    return accounts.some((a) => a.access_rights === 'FULL_ACCESS');
  } catch {
    return false;
  }
}

export async function placeBrokerOrder(order: BrokerOrderRequest): Promise<{ orderId: number; price: number }> {
  return brokerJson('/orders/', { method: 'POST', body: JSON.stringify(order) });
}

export async function fetchBrokerPositions(): Promise<BrokerPosition[]> {
  const rows = await brokerJson<Record<string, unknown>[]>('/positions/');
  return rows.map((r) => {
    const td = (r.trade_data ?? {}) as Record<string, unknown>;
    return {
      id: Number(r.position_id),
      symbol: String(r.symbol ?? ''),
      side: td.trade_side === 'SELL' ? 'SELL' : 'BUY',
      volume: Number(td.volume ?? 0),
      price: n(r.price),
      stopLoss: n(r.stop_loss),
      takeProfit: n(r.take_profit),
      currentPrice: n(r.current_price),
      profit: typeof r.profit === 'number' ? r.profit : null,
    };
  });
}

export async function fetchBrokerOrders(): Promise<BrokerOrder[]> {
  const rows = await brokerJson<Record<string, unknown>[]>('/orders/open');
  return rows.map((r) => {
    const td = (r.trade_data ?? {}) as Record<string, unknown>;
    return {
      id: Number(r.order_id),
      symbol: String(r.symbol ?? ''),
      side: td.trade_side === 'SELL' ? 'SELL' : 'BUY',
      type: String(r.order_type ?? ''),
      volume: Number(td.volume ?? 0),
      price: n(r.limit_price) ?? n(r.stop_price),
      stopLoss: n(r.stop_loss),
      takeProfit: n(r.take_profit),
    };
  });
}

export async function closeBrokerPosition(id: number): Promise<void> {
  await brokerJson(`/positions/${id}/close`, { method: 'POST' });
}

export async function cancelBrokerOrder(id: number): Promise<void> {
  await brokerJson(`/orders/${id}`, { method: 'DELETE' });
}
