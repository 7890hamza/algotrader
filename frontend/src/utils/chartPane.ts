/**
 * Several charts at once (2 side by side, or 4 in a grid). Every extra chart is the same app
 * in an iframe with `?pane=N`, so it has its own symbol, timeframe and indicators. Its saved
 * settings use their own storage keys and start from the first chart's until changed; in the
 * 4-chart grid an extra chart that has no symbol of its own yet opens on NQ, MES or MNQ.
 */
const params = typeof location === 'undefined' ? null : new URLSearchParams(location.search);

export const CHART_PANE = params?.get('pane') ?? '1';
export const IS_SECOND_PANE = CHART_PANE !== '1';
export const CHART_LAYOUT_KEY = 'algotrader_chart_layout';
export type ChartLayout = 'single' | 'split' | 'quad';
export const CHART_LAYOUTS: readonly ChartLayout[] = ['single', 'split', 'quad'];
/** Extra chart panes for each layout (the first chart is the page itself). */
export const EXTRA_PANES: Record<ChartLayout, string[]> = { single: [], split: ['2'], quad: ['2', '3', '4'] };
/** Symbol an extra chart opens on the first time, in the 4-chart grid. */
export const PANE_DEFAULT_SYMBOL: Record<string, string> = { '2': 'NQ', '3': 'MES', '4': 'MNQ' };
export const PANE_SYMBOL = params?.get('symbol') ?? null;

export function paneKey(key: string): string {
  return IS_SECOND_PANE ? `${key}__pane${CHART_PANE}` : key;
}

export function paneUrl(pane: string, defaultSymbol?: string): string {
  const url = new URL(typeof location === 'undefined' ? 'http://localhost/' : location.href);
  url.search = `?pane=${pane}${defaultSymbol ? `&symbol=${encodeURIComponent(defaultSymbol)}` : ''}`;
  url.hash = '';
  return url.toString();
}

export function secondPaneUrl(): string {
  return paneUrl('2');
}

/** True when this extra chart has not saved a symbol of its own yet. */
export function paneHasOwnSymbol(storageKey: string): boolean {
  try {
    return localStorage.getItem(paneKey(storageKey)) !== null;
  } catch {
    return true;
  }
}
