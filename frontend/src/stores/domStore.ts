import { defineStore } from 'pinia';
import { ref, shallowRef } from 'vue';

import type { DomState } from '@/utils/dom/memoryDom';
import { getStoredState, setStoredState } from '@/utils/localStorage';

const VISIBLE_KEY = 'algotrader_memory_dom_visible';
const RETRY_MS = 3_000;

/** The memory DOM panel: shown or hidden (remembered), and the live feed from dom-service. */
export const useDomStore = defineStore('memoryDom', () => {
  const visible = ref<boolean>(getStoredState<boolean>(VISIBLE_KEY) ?? false);
  const state = shallowRef<DomState | null>(null);
  /** the app reached dom-service (NinjaTrader itself is `state.connected`) */
  const online = ref(false);
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;

  function url(): string {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${window.location.host}/api/dom/ws`;
  }

  function open(): void {
    if (socket || !visible.value) return;
    const ws = new WebSocket(url());
    socket = ws;
    ws.onopen = () => { online.value = true; };
    ws.onmessage = (m: MessageEvent<string>) => {
      try {
        state.value = JSON.parse(m.data) as DomState;
      } catch {
        /* ignore a bad frame */
      }
    };
    ws.onclose = () => {
      if (socket === ws) socket = null;
      online.value = false;
      if (visible.value) retry = setTimeout(open, RETRY_MS);
    };
  }

  function close(): void {
    if (retry) clearTimeout(retry);
    retry = null;
    const ws = socket;
    socket = null;
    ws?.close();
    online.value = false;
  }

  function setVisible(on: boolean): void {
    visible.value = on;
    setStoredState(VISIBLE_KEY, on);
    if (on) open();
    else close();
  }

  function toggle(): void {
    setVisible(!visible.value);
  }

  if (visible.value) open();

  return { visible, state, online, setVisible, toggle };
});
