import { defineStore } from 'pinia';
import { computed, ref, shallowRef, watch } from 'vue';

import { fetchGamePlan } from '@/api/gamePlanClient';
import { useReplayStore } from '@/stores/replayStore';
import type { DayPlan } from '@/utils/chart/gamePlan';
import { getStoredState, setStoredState } from '@/utils/localStorage';
import { IS_REPLAY } from '@/utils/replay';
import { cmeDay } from '@/utils/setups';

/** Replay: the plan as it stood at the cursor (later hits not hit yet, price path cut there). */
export function planAt(plan: DayPlan, t: number): DayPlan {
  // 5-minute buckets that are complete by the end of the cursor's minute
  const path = (plan.path ?? []).filter((p) => p[0] + 300_000 <= t + 60_000);
  const lastBar = path[path.length - 1];
  const ctx = { ...plan.ctx };
  const span = (from: number) => {
    const xs = path.filter((p) => p[0] >= from);
    return xs.length ? { hi: Math.max(...xs.map((p) => p[1])), lo: Math.min(...xs.map((p) => p[2])) } : null;
  };
  const day = span(plan.start);
  if (day) { ctx.dayHigh = day.hi; ctx.dayLow = day.lo; } else { delete ctx.dayHigh; delete ctx.dayLow; }
  const rth = t >= ctx.rth0 ? span(ctx.rth0) : null;
  if (rth) { ctx.rthHigh = rth.hi; ctx.rthLow = rth.lo; } else { delete ctx.rthOpen; delete ctx.rthHigh; delete ctx.rthLow; delete ctx.setupRth; }
  if (t < ctx.ib1) delete ctx.ib;
  if (t < plan.start + 11 * 3_600_000) delete ctx.aln; // the ALN pattern posts at 5 AM New York
  return {
    ...plan,
    ctx,
    path,
    last: lastBar ? { t: Math.min(t, plan.end), close: lastBar[3] } : null,
    levels: plan.levels
      .filter((l) => l.frm <= t)
      .map((l) => (l.hitAt !== null && l.hitAt > t ? { ...l, hitAt: null, never: false } : l.never && t < l.until ? { ...l, never: false } : l)),
  };
}

const VISIBLE_KEY = 'algotrader_game_plan_visible';
const AHEAD_KEY = 'algotrader_game_plan_ahead';

/** Heads-up bracket: how many stats, within how many points (per market family), before it shows. */
export interface AheadSettings { minCount: number; reachES: number; reachNQ: number }
const AHEAD_DEFAULT: AheadSettings = { minCount: 4, reachES: 12, reachNQ: 50 };
const REFRESH_MS = 30_000;

/** The Game Plan panel: shown or hidden (remembered), and the day plan it polls every 30 s. */
export const useGamePlanStore = defineStore('gamePlan', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  const raw = shallowRef<DayPlan | null>(null);
  const ahead = ref<AheadSettings>({ ...AHEAD_DEFAULT, ...(getStoredState<Partial<AheadSettings>>(AHEAD_KEY) ?? {}) });
  function setAhead(next: Partial<AheadSettings>): void {
    const merged = { ...ahead.value, ...next };
    if (!(merged.minCount >= 2) || !(merged.reachES > 0) || !(merged.reachNQ > 0)) return;
    ahead.value = merged;
    setStoredState(AHEAD_KEY, merged);
  }
  const replay = IS_REPLAY ? useReplayStore() : null;
  const plan = computed<DayPlan | null>(() => (raw.value && replay ? planAt(raw.value, replay.cursorMs) : raw.value));
  /** Replay: the CME day being played back (the plan reloads when playback crosses into the next). */
  const replayDay = computed(() => (replay && Number.isFinite(replay.cursorMs) ? cmeDay(replay.cursorMs) : null));
  const error = ref<string | null>(null);
  const loading = ref(false);
  let symbol: string | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refresh(): Promise<void> {
    if (!symbol || !visible.value) return;
    const asked = symbol;
    loading.value = true;
    try {
      const next = await fetchGamePlan(asked, replayDay.value ? { day: replayDay.value } : {});
      if (asked === symbol) {
        raw.value = next;
        error.value = null;
      }
    } catch (e) {
      if (asked === symbol) error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  function restart(): void {
    if (timer) clearInterval(timer);
    timer = null;
    if (!visible.value || !symbol) return;
    void refresh();
    if (!IS_REPLAY) timer = setInterval(() => void refresh(), REFRESH_MS); // Replay: past days don't change
  }
  if (IS_REPLAY) watch(replayDay, (d, before) => { if (d !== before) void refresh(); });

  function setSymbol(next: string | null): void {
    if (next === symbol) return;
    symbol = next;
    raw.value = null;
    restart();
  }

  function setVisible(on: boolean): void {
    visible.value = on;
    setStoredState(VISIBLE_KEY, on);
    if (!on) raw.value = null;
    restart();
  }

  function toggle(): void {
    setVisible(!visible.value);
  }

  return { visible, plan, error, loading, refresh, setSymbol, setVisible, toggle, ahead, setAhead };
});
