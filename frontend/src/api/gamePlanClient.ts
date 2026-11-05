import type { DayPlan } from '@/utils/chart/gamePlan';

import { parseJsonResponse, withQuery } from './http';

const GAME_PLAN_BASE_URL = '/api/indicator-api/game-plan';

function isDayPlan(value: unknown): value is DayPlan {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<DayPlan>;
  return Array.isArray(v.levels) && typeof v.start === 'number' && typeof v.sessions === 'object';
}

/** The day's stat targets with their odds, hits and carry-over (the current CME day by default). */
export async function fetchGamePlan(symbol: string, options: { day?: string; exchange?: string | null } = {}): Promise<DayPlan> {
  const payload = await parseJsonResponse(
    await fetch(withQuery(`${GAME_PLAN_BASE_URL}/${encodeURIComponent(symbol)}`, { day: options.day, exchange: options.exchange ?? undefined })),
    'Failed to fetch the game plan',
  );
  if (!isDayPlan(payload)) throw new Error('Invalid game plan response');
  return payload;
}
