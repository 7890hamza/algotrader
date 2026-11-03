export const DEFAULT_CHART_INTERACTION_MODE = 'pan';

/** pan / measure, or long / short: the next click places a risk-to-reward plan. */
export type ChartInteractionMode = 'pan' | 'measure' | 'long' | 'short';

export const CHART_INTERACTION_MODES: readonly ChartInteractionMode[] = ['pan', 'measure', 'long', 'short'];
