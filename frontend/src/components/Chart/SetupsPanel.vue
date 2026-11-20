<template>
  <div v-if="indicator" class="setups-panel" data-testid="setups-panel">
    <div class="row head">
      <b>Setups</b>
      <span>{{ done.length }} trades · {{ hits }} hit {{ target }}</span>
      <span :class="pts >= 0 ? 'win' : 'loss'">{{ pts >= 0 ? '+' : '' }}{{ pts.toFixed(2) }} pts</span>
      <span v-if="dollars !== null" :class="pts >= 0 ? 'win' : 'loss'">{{ money(dollars) }} <small>1 {{ symbol }}</small></span>
    </div>
    <div v-for="s in perSetup" :key="s.id" class="row">
      <span class="tag" :class="s.dir > 0 ? 'long' : 'short'">{{ s.id }} {{ s.dir > 0 ? '▲' : '▼' }}</span>
      <span class="name">{{ s.name }}</span>
      <span>{{ s.n }}</span>
      <span :class="s.pts >= 0 ? 'win' : 'loss'">{{ s.pts >= 0 ? '+' : '' }}{{ s.pts.toFixed(1) }}</span>
    </div>
    <div v-if="last" class="last">
      Last: {{ last.id }} {{ last.dir > 0 ? 'long' : 'short' }} {{ last.how === 'target' ? `hit ${target} ✓` : last.how === 'stop' ? 'stopped ✕' : 'timed out' }}
      <span :class="last.pts >= 0 ? 'win' : 'loss'">{{ last.pts >= 0 ? '+' : '' }}{{ last.pts }}</span>
    </div>
    <div class="note">Trades on the bars loaded{{ replay.active ? ', up to the replay cursor' : '' }}. Scroll back to load more.</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useIndicatorsStore } from '@/stores/indicatorsStore';
import { useReplayStore } from '@/stores/replayStore';
import { POINT_VALUE, SETUPS, tradesFrom } from '@/utils/setups';

defineOptions({ name: 'SetupsPanel' });

const indicatorsStore = useIndicatorsStore();
const replay = useReplayStore();
const market = useCurrentMarketStore();
const indicator = computed(() => indicatorsStore.all.find((i) => i.info.guide?.kind === 'setups') ?? null);
const target = computed(() => Number(indicator.value?.parameters?.target?.value ?? indicator.value?.parameters?.target?.default ?? 10));
const symbol = computed(() => String(market.symbol ?? '').toUpperCase());
const done = computed(() => {
  const ind = indicator.value;
  if (!ind) return [];
  void ind.dataVersion;
  const cutoff = replay.active ? replay.cursorMs : Number.POSITIVE_INFINITY;
  return tradesFrom(ind.data).filter((t) => t.exitMs <= cutoff);
});
const pts = computed(() => done.value.reduce((a, t) => a + t.pts, 0));
const hits = computed(() => done.value.filter((t) => t.how === 'target').length);
const dollars = computed(() => (POINT_VALUE[symbol.value] ? pts.value * POINT_VALUE[symbol.value] : null));
const perSetup = computed(() => SETUPS.map((s) => {
  const mine = done.value.filter((t) => t.id === s.id);
  return { ...s, n: mine.length, pts: mine.reduce((a, t) => a + t.pts, 0) };
}).filter((s) => s.n > 0));
const last = computed(() => done.value[done.value.length - 1] ?? null);
const money = (v: number): string => `${v < 0 ? '−' : '+'}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`;
</script>

<style scoped>
.setups-panel {
  position: absolute; left: 10px; bottom: 44px; z-index: 6; min-width: 250px; max-width: 320px;
  padding: 8px 10px; border-radius: 8px; background: rgba(13, 16, 23, 0.92); border: 1px solid rgba(255, 255, 255, 0.08);
  color: #d1d4dc; font-size: 12px; font-variant-numeric: tabular-nums; display: flex; flex-direction: column; gap: 3px; pointer-events: none;
}
.row { display: flex; gap: 8px; align-items: baseline; }
.row.head { flex-wrap: wrap; border-bottom: 1px solid rgba(255, 255, 255, 0.07); padding-bottom: 4px; margin-bottom: 2px; }
.row.head b { color: #e3ad42; }
.name { flex: 1; color: #9aa1ac; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag { font-weight: 600; border-radius: 4px; padding: 0 4px; font-size: 11px; }
.tag.long { background: rgba(47, 191, 143, 0.18); color: #2fbf8f; }
.tag.short { background: rgba(224, 86, 108, 0.18); color: #e0566c; }
.win { color: #2fbf8f; } .loss { color: #e0566c; }
small { color: #8b93a1; }
.last { color: #9aa1ac; }
.note { color: #6b7280; font-size: 11px; }
</style>
