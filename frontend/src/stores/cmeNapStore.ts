import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_cme_nap_visible';

/** On / off for the "CME closed" overlay (Hyperliquid's price while CME is shut). */
export const useCmeNapStore = defineStore('cmeNap', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  /** what the overlay is showing, for the top bar's tooltip */
  const status = ref('');
  /** Replay / live: finished catch-up trades in the loaded candles, e.g. 'Catch-up trades: 3 of 4 won · +61 pts' */
  const tradeScore = ref('');
  function toggle(): void {
    visible.value = !visible.value;
    setStoredState(VISIBLE_KEY, visible.value);
  }
  return { visible, status, tradeScore, toggle };
});
