import { defineStore } from 'pinia';
import { ref, shallowRef } from 'vue';

import { fetchGamePlan } from '@/api/gamePlanClient';
import type { DayPlan } from '@/utils/chart/gamePlan';
import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_game_plan_visible';
const REFRESH_MS = 30_000;

/** The Game Plan panel: shown or hidden (remembered), and the day plan it polls every 30 s. */
export const useGamePlanStore = defineStore('gamePlan', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  const plan = shallowRef<DayPlan | null>(null);
  const error = ref<string | null>(null);
  const loading = ref(false);
  let symbol: string | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refresh(): Promise<void> {
    if (!symbol || !visible.value) return;
    const asked = symbol;
    loading.value = true;
    try {
      const next = await fetchGamePlan(asked);
      if (asked === symbol) {
        plan.value = next;
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
    timer = setInterval(() => void refresh(), REFRESH_MS);
  }

  function setSymbol(next: string | null): void {
    if (next === symbol) return;
    symbol = next;
    plan.value = null;
    restart();
  }

  function setVisible(on: boolean): void {
    visible.value = on;
    setStoredState(VISIBLE_KEY, on);
    if (!on) plan.value = null;
    restart();
  }

  function toggle(): void {
    setVisible(!visible.value);
  }

  return { visible, plan, error, loading, refresh, setSymbol, setVisible, toggle };
});
