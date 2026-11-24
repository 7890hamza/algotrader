import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_gex_visible';
const MODE_KEY = 'algotrader_gex_mode';

/**
 * On / off for the options levels, and which kind:
 *   walls - the STS QQQ / SPY open-interest walls (scripts/oi_walls.py), drawn as steps through the day
 *   gamma - gamma exposure from SPX / NDX (scripts/gex.py)
 */
export const useGexStore = defineStore('gex', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  const mode = ref<'walls' | 'gamma'>(getStoredState<'walls' | 'gamma'>(MODE_KEY) ?? 'walls');
  function toggle(): void {
    visible.value = !visible.value;
    setStoredState(VISIBLE_KEY, visible.value);
  }
  function setMode(m: 'walls' | 'gamma'): void {
    mode.value = m;
    setStoredState(MODE_KEY, m);
  }
  return { visible, mode, toggle, setMode };
});
