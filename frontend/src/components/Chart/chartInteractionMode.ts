export const DEFAULT_CHART_INTERACTION_MODE = 'pan';

/**
 * pan / measure; long / short: the next click places a risk-to-reward plan; retrace: the next
 * two clicks place a retracement (leg start, then leg end).
 */
export type ChartInteractionMode = 'pan' | 'measure' | 'long' | 'short' | 'retrace';

export const CHART_INTERACTION_MODES: readonly ChartInteractionMode[] = ['pan', 'measure', 'long', 'short', 'retrace'];
