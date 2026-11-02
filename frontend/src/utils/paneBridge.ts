/**
 * Messages between the main chart page and the second chart (an iframe, `?pane=2`).
 * The main page owns the top bar; the second chart reports clicks and its symbol /
 * timeframe, and the main page asks it to open a modal, change timeframe or mode.
 */
export const PANE_MESSAGE_SOURCE = 'algotrader-pane';

export type PaneMessage =
  | { type: 'activate' }
  | { type: 'state'; symbol: string | null; timeframe: string }
  | { type: 'open-modal'; name: string }
  | { type: 'set-timeframe'; value: string }
  | { type: 'set-interaction-mode'; mode: string };

export function postPaneMessage(target: Window | null | undefined, message: PaneMessage): void {
  target?.postMessage({ source: PANE_MESSAGE_SOURCE, ...message }, window.location.origin);
}

export function readPaneMessage(event: MessageEvent): PaneMessage | null {
  if (event.origin !== window.location.origin) return null;
  const data = event.data as { source?: unknown; type?: unknown } | null;
  if (!data || data.source !== PANE_MESSAGE_SOURCE || typeof data.type !== 'string') return null;
  return data as unknown as PaneMessage;
}
