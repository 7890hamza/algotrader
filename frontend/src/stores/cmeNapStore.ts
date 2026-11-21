import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_cme_nap_visible';

/** On / off for the "CME closed" overlay (Hyperliquid's price while CME is shut). */
export const useCmeNapStore = defineStore('cmeNap', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  /** what the overlay is showing, for the top bar's tooltip */
  const status = ref('');
  function toggle(): void {
    visible.value = !visible.value;
    setStoredState(VISIBLE_KEY, visible.value);
  }
  return { visible, status, toggle };
});
