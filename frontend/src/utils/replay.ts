/**
 * Replay: the regular chart opened at a past moment (`?replay=<epoch ms>`), for playing back days
 * and weeks. It loads the week from that moment on (or up to now), shows bars only up to the
 * replay cursor, and leaves live updates off. Leaving Replay reloads the live chart, so the live
 * chart's own loading is untouched.
 */
const params = typeof location === 'undefined' ? null : new URLSearchParams(location.search);
const raw = Number(params?.get('replay'));

export const REPLAY_START_MS: number | null = Number.isFinite(raw) && raw > 0 ? raw : null;
export const IS_REPLAY = REPLAY_START_MS !== null;
export const REPLAY_WINDOW_MS = 7 * 86_400_000;
/** Bars per request in Replay: a full week of 1-minute bars. */
export const REPLAY_FETCH_LIMIT = 12_000;

export function replayEndMs(now = Date.now()): number | null {
  return REPLAY_START_MS === null ? null : Math.min(REPLAY_START_MS + REPLAY_WINDOW_MS, now - 60_000);
}

/** The app's URL in Replay at `ms`, or back to the live chart for null. Keeps other params (pane). */
export function replayUrl(ms: number | null, href = typeof location === 'undefined' ? 'http://localhost/' : location.href): string {
  const url = new URL(href);
  if (ms === null) url.searchParams.delete('replay');
  else url.searchParams.set('replay', String(Math.floor(ms)));
  url.hash = '';
  return url.toString();
}

/** 6 PM New York on the evening before `day` (YYYY-MM-DD): the start of that CME trading day. */
export function cmeDayStartMs(day: string): number {
  const noonUtc = Date.parse(`${day}T12:00:00Z`);
  const nyHour = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }).format(new Date(noonUtc)));
  const offsetMs = (nyHour - 12) * 3_600_000;
  return Date.parse(`${day}T00:00:00Z`) - offsetMs - 6 * 3_600_000;
}
