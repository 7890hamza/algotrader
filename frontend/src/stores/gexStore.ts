import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_gex_visible';

/** On / off for the GEX (gamma exposure) levels from scripts/gex.py. */
export const useGexStore = defineStore('gex', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  function toggle(): void {
    visible.value = !visible.value;
    setStoredState(VISIBLE_KEY, visible.value);
  }
  return { visible, toggle };
});
