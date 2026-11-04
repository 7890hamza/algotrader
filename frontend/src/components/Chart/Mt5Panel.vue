<template>
  <div v-if="enabled && (positions.length || orders.length || error)" class="mt5" data-testid="mt5-panel">
    <div class="mt5-head">
      <span>MT5 demo</span>
      <span v-if="totalProfit !== null" :class="totalProfit >= 0 ? 'mt5-win' : 'mt5-loss'">{{ money(totalProfit) }}</span>
    </div>
    <div v-for="p in positions" :key="`p${p.id}`" class="mt5-row">
      <span :class="p.side === 'BUY' ? 'mt5-win' : 'mt5-loss'">{{ p.side }} {{ p.volume }}</span>
      <span>{{ p.symbol }} @ {{ price(p.price) }}</span>
      <span class="mt5-dim">SL {{ price(p.stopLoss) }} · TP {{ price(p.takeProfit) }}</span>
      <span :class="(p.profit ?? 0) >= 0 ? 'mt5-win' : 'mt5-loss'">{{ p.profit === null ? '' : money(p.profit) }}</span>
      <button type="button" class="mt5-btn" :data-testid="`close-${p.id}`" @click="act(`p${p.id}`, () => closeBrokerPosition(p.id))">
        {{ armed === `p${p.id}` ? 'Sure?' : 'Close' }}
      </button>
    </div>
    <div v-for="o in orders" :key="`o${o.id}`" class="mt5-row mt5-row--order">
      <span :class="o.side === 'BUY' ? 'mt5-win' : 'mt5-loss'">{{ o.side }} {{ o.type }} {{ o.volume }}</span>
      <span>{{ o.symbol }} @ {{ price(o.price) }}</span>
      <span class="mt5-dim">SL {{ price(o.stopLoss) }} · TP {{ price(o.takeProfit) }}</span>
      <span class="mt5-dim">working</span>
      <button type="button" class="mt5-btn" :data-testid="`cancel-${o.id}`" @click="act(`o${o.id}`, () => cancelBrokerOrder(o.id))">
        {{ armed === `o${o.id}` ? 'Sure?' : 'Cancel' }}
      </button>
    </div>
    <div v-if="error" class="mt5-loss mt5-err">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import {
  cancelBrokerOrder,
  closeBrokerPosition,
  fetchBrokerOrders,
  fetchBrokerPositions,
  fetchTradingEnabled,
  type BrokerOrder,
  type BrokerPosition,
} from '@/api/brokerClient';

defineOptions({ name: 'Mt5Panel' });

const POLL_MS = 2000;
const IDLE_MS = 15000;

const enabled = ref(false);
const positions = ref<BrokerPosition[]>([]);
const orders = ref<BrokerOrder[]>([]);
const error = ref('');
const armed = ref<string | null>(null);
let timer: ReturnType<typeof setTimeout> | null = null;
let stopped = false;

const totalProfit = computed(() => (positions.value.length ? positions.value.reduce((s, p) => s + (p.profit ?? 0), 0) : null));
const price = (v: number | null): string => (v === null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: 5 }));
const money = (v: number): string => `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

async function refresh(): Promise<void> {
  if (stopped) return;
  try {
    if (!enabled.value) enabled.value = await fetchTradingEnabled();
    if (enabled.value) {
      [positions.value, orders.value] = await Promise.all([fetchBrokerPositions(), fetchBrokerOrders()]);
    }
  } catch {
    enabled.value = false;
  }
  timer = setTimeout(() => void refresh(), enabled.value ? POLL_MS : IDLE_MS);
}

/** Close / cancel needs a second click ("Sure?") within a few seconds. */
async function act(key: string, run: () => Promise<void>): Promise<void> {
  if (armed.value !== key) {
    armed.value = key;
    setTimeout(() => { if (armed.value === key) armed.value = null; }, 4000);
    return;
  }
  armed.value = null;
  try {
    await run();
    error.value = '';
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'MT5 did not do it';
  }
  if (timer) clearTimeout(timer);
  void refresh();
}

onMounted(() => void refresh());
onBeforeUnmount(() => {
  stopped = true;
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.mt5 {
  position: absolute;
  bottom: 44px;
  right: 80px;
  z-index: 7;
  min-width: 360px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(19, 23, 34, 0.92);
  color: #d1d4dc;
  font-size: 12px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mt5-head { display: flex; justify-content: space-between; font-weight: 600; color: #e6e6e6; }
.mt5-row { display: grid; grid-template-columns: auto auto 1fr auto auto; gap: 8px; align-items: center; font-variant-numeric: tabular-nums; }
.mt5-dim { color: #8a919c; font-size: 11px; }
.mt5-win { color: #3fb950; }
.mt5-loss { color: #e0574a; }
.mt5-btn { background: transparent; border: 1px solid rgba(255, 255, 255, 0.2); color: #d1d4dc; border-radius: 4px; padding: 1px 8px; cursor: pointer; font-size: 11px; }
.mt5-btn:hover { border-color: rgba(255, 255, 255, 0.45); }
.mt5-err { font-size: 11px; }
</style>
