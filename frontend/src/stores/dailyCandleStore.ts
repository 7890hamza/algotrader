import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_daily_candle_visible';
const WHO_KEY = 'algotrader_daily_candle_who';

export type DcWho = 'austin' | 'riley' | 'both';

/** On / off and whose view for the "Daily candle" overlay (Austin's levels vs Riley's boxes). */
export const useDailyCandleStore = defineStore('dailyCandle', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  const who = ref<DcWho>(getStoredState<DcWho>(WHO_KEY) ?? 'both');
  /** finished days in the loaded candles, e.g. 'Austin 3 of 5 · Riley 2 of 4' */
  const score = ref('');
  function toggle(): void {
    visible.value = !visible.value;
    setStoredState(VISIBLE_KEY, visible.value);
  }
  function setWho(w: DcWho): void {
    who.value = w;
    setStoredState(WHO_KEY, w);
  }
  return { visible, who, score, toggle, setWho };
});
