<template>
  <aside class="md" data-testid="memory-dom-panel" aria-label="Memory DOM">
    <header class="md-head">
      <span class="md-title">Memory DOM</span>
      <span class="md-sym">{{ st?.sym || '' }}</span>
      <span class="md-dot" :class="status.cls" :title="status.text" />
      <span class="md-status">{{ status.text }}</span>
      <button class="md-btn" type="button" :class="{ 'md-btn--on': follow }" title="Keep the last price in the middle" @click="recenter">Center</button>
      <button class="md-x" type="button" aria-label="Hide the memory DOM" @click="store.setVisible(false)">×</button>
    </header>

    <p v-if="!st" class="md-empty">
      {{ store.online ? 'Waiting for data…' : 'Connecting to the DOM service…' }}
    </p>
    <p v-else-if="!st.connected && !st.bids.length" class="md-empty">
      Waiting for NinjaTrader. Add the AlgoTraderDomBridge indicator to an ES chart in NinjaTrader 8.
    </p>

    <template v-if="st && rows.length">
      <div class="md-grid md-cols" role="row">
        <span>Sold</span><span>Bid</span><span>Price</span><span>Ask</span><span>Bought</span><span>Memory</span><span>What price did</span>
      </div>
      <div ref="ladder" class="md-ladder" data-testid="memory-dom-ladder" @wheel.prevent="onWheel">
        <div
          v-for="r in rows"
          :key="r.key"
          class="md-grid md-row"
          :class="{ 'md-row--last': r.isLast, 'md-row--mem': r.events.length }"
          :title="r.events.length ? r.events.map(eventText).join('\n') : undefined"
          data-testid="memory-dom-row"
        >
          <span class="md-vol md-sold">{{ r.sold ?? '' }}</span>
          <span class="md-size md-bid" :class="{ 'md-big': r.big?.side === 'b' }">
            <i v-if="r.bid" class="md-bar md-bar--bid" :style="{ width: barW(r.bid) }" />
            <b>{{ r.bid ?? '' }}</b>
          </span>
          <span class="md-price">{{ fmtPrice(r.price) }}</span>
          <span class="md-size md-ask" :class="{ 'md-big': r.big?.side === 'a' }">
            <i v-if="r.ask" class="md-bar md-bar--ask" :style="{ width: barW(r.ask) }" />
            <b>{{ r.ask ?? '' }}</b>
          </span>
          <span class="md-vol md-bought">{{ r.bought ?? '' }}</span>
          <span class="md-mem">
            <em v-if="r.badge" class="md-badge" :class="`md-badge--${r.badge.kind}`">{{ r.badge.text }}</em>
            <em v-else-if="r.big" class="md-badge md-badge--live">resting{{ r.big.holds ? ` · held ${r.big.holds}x` : '' }}</em>
          </span>
          <span class="md-note">{{ r.note ?? '' }}</span>
        </div>
      </div>
      <footer class="md-foot">
        <p v-for="line in lessons" :key="line.text" class="md-lesson">{{ line.text }} <span>({{ line.n }})</span></p>
        <p v-if="!lessons.length" class="md-lesson">Lessons show up here once big orders have been watched for 5 minutes.</p>
        <p class="md-legend">
          <em class="md-badge md-badge--pulled">pulled</em> left without trading
          <em class="md-badge md-badge--filled">filled</em> traded away
          <em class="md-badge md-badge--held">held</em> got hit and stayed. Read-only, no orders.
        </p>
      </footer>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

import { useDomStore } from '@/stores/domStore';
import { buildLadder, eventText, fmtPrice, statLines } from '@/utils/dom/memoryDom';

defineOptions({ name: 'MemoryDomPanel' });

const ROWS = 44;
const store = useDomStore();
const st = computed(() => store.state);
const follow = ref(true);
const manualTop = ref<number | null>(null);

const top = computed<number | null>(() => {
  const s = st.value;
  if (!s) return null;
  const tick = s.tick || 0.25;
  if (!follow.value && manualTop.value !== null) return manualTop.value;
  const mid = s.last ?? s.bid ?? s.asks[0]?.[0] ?? s.bids[0]?.[0] ?? null;
  return mid === null ? null : mid + Math.floor(ROWS / 2) * tick;
});

const rows = computed(() => (st.value && top.value !== null ? buildLadder(st.value, top.value, ROWS) : []));
const maxSize = computed(() => Math.max(1, ...rows.value.map((r) => Math.max(r.bid ?? 0, r.ask ?? 0))));
const barW = (v: number): string => `${Math.min(100, Math.round((v / maxSize.value) * 100))}%`;
const lessons = computed(() => statLines(st.value?.stats ?? []));

const status = computed(() => {
  if (!store.online) return { cls: 'md-dot--off', text: 'service offline' };
  if (!st.value?.connected) return { cls: 'md-dot--wait', text: 'NinjaTrader not connected' };
  return { cls: 'md-dot--on', text: 'live' };
});

function onWheel(e: WheelEvent): void {
  const s = st.value;
  if (!s || top.value === null) return;
  const tick = s.tick || 0.25;
  manualTop.value = top.value + (e.deltaY > 0 ? -3 : 3) * tick;
  follow.value = false;
}

function recenter(): void {
  follow.value = true;
  manualTop.value = null;
}
</script>

<style scoped>
.md {
  width: 520px;
  flex: 0 0 520px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #131722;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 10px;
  color: #d7dbe3;
  font-size: 12px;
  font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}
.md-head { display: flex; align-items: center; gap: 8px; }
.md-title { font-weight: 600; font-size: 13px; }
.md-sym { color: #8a919c; font-size: 11px; }
.md-dot { width: 7px; height: 7px; border-radius: 50%; margin-left: auto; }
.md-dot--on { background: #2fb67c; }
.md-dot--wait { background: #e9c46a; }
.md-dot--off { background: #e0574a; }
.md-status { color: #8a919c; font-size: 11px; }
.md-btn { background: transparent; border: 1px solid rgba(255, 255, 255, 0.14); color: #8a919c; border-radius: 4px; font-size: 11px; padding: 1px 8px; cursor: pointer; }
.md-btn--on { color: #d7dbe3; border-color: rgba(255, 255, 255, 0.3); }
.md-x { background: transparent; border: 0; color: #8a919c; font-size: 16px; line-height: 1; cursor: pointer; padding: 0 2px; }
.md-x:hover { color: #d7dbe3; }
.md-empty { color: #8a919c; margin: 0; line-height: 1.5; }
.md-grid { display: grid; grid-template-columns: 38px 58px 64px 58px 38px 74px minmax(0, 1fr); align-items: center; }
.md-cols { color: #8a919c; font-size: 10.5px; text-align: center; padding-bottom: 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }
.md-cols span:last-child { text-align: left; padding-left: 6px; }
.md-ladder { flex: 1 1 auto; min-height: 0; overflow: hidden; font-variant-numeric: tabular-nums; }
.md-row { height: 17px; border-bottom: 1px solid rgba(255, 255, 255, 0.035); text-align: center; }
.md-row--mem { background: rgba(255, 255, 255, 0.02); }
.md-row--last .md-price { background: #e9c46a; color: #131722; font-weight: 600; }
.md-price { background: rgba(255, 255, 255, 0.05); height: 100%; line-height: 17px; }
.md-size { position: relative; height: 100%; line-height: 17px; }
.md-size b { position: relative; font-weight: 500; }
.md-bid b { color: #7cb7f0; }
.md-ask b { color: #f08a80; }
.md-bar { position: absolute; top: 2px; bottom: 2px; opacity: 0.22; }
.md-bar--bid { right: 0; background: #378add; }
.md-bar--ask { left: 0; background: #e24b4a; }
.md-big { outline: 1px solid rgba(233, 196, 106, 0.8); outline-offset: -1px; }
.md-big b { font-weight: 700; }
.md-vol { color: #8a919c; font-size: 11px; }
.md-mem { text-align: left; padding-left: 4px; }
.md-note { text-align: left; padding-left: 6px; color: #a9b0bb; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.md-badge { font-style: normal; font-size: 10.5px; padding: 0 5px; border-radius: 3px; white-space: nowrap; }
.md-badge--pulled { background: rgba(216, 90, 48, 0.22); color: #f0997b; }
.md-badge--filled { background: rgba(127, 119, 221, 0.25); color: #afa9ec; }
.md-badge--held { background: rgba(29, 158, 117, 0.25); color: #5dcaa5; }
.md-badge--live { background: rgba(233, 196, 106, 0.18); color: #e9c46a; }
.md-foot { border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 6px; display: flex; flex-direction: column; gap: 2px; }
.md-lesson { margin: 0; color: #a9b0bb; font-size: 11px; }
.md-lesson span { color: #6b7280; }
.md-legend { margin: 4px 0 0; color: #6b7280; font-size: 10.5px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
</style>
