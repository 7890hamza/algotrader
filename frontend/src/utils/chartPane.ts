/**
 * Side-by-side charts. The second chart is the same app in an iframe with `?pane=2`,
 * so it has its own symbol, timeframe and indicators. Its saved settings use their
 * own storage keys and start from the first chart's until changed.
 */
const params = typeof location === 'undefined' ? null : new URLSearchParams(location.search);

export const CHART_PANE = params?.get('pane') ?? '1';
export const IS_SECOND_PANE = CHART_PANE !== '1';
export const CHART_LAYOUT_KEY = 'algotrader_chart_layout';
export type ChartLayout = 'single' | 'split';

export function paneKey(key: string): string {
  return IS_SECOND_PANE ? `${key}__pane${CHART_PANE}` : key;
}

export function secondPaneUrl(): string {
  const url = new URL(typeof location === 'undefined' ? 'http://localhost/' : location.href);
  url.search = '?pane=2';
  url.hash = '';
  return url.toString();
}
