<template>
  <aside class="gp" data-testid="game-plan-panel" aria-label="Game plan">
    <header class="gp-head">
      <span class="gp-title">Game plan</span>
      <span class="gp-time">{{ timeLabel }}</span>
      <button class="gp-x" type="button" aria-label="Hide the game plan" @click="store.setVisible(false)">×</button>
    </header>

    <p v-if="!plan && store.error" class="gp-empty">Couldn't load the game plan. It retries every 30 seconds.</p>
    <p v-else-if="!plan" class="gp-empty">Loading today's targets…</p>

    <template v-else-if="board">
      <section class="gp-day">
        <span v-if="board.dayType" class="gp-chip" :class="`gp-chip--${board.dayType.tone}`">{{ board.dayType.label }}</span>
        <span v-if="board.move !== null" class="gp-move" :class="board.move < 0 ? 'gp-down' : 'gp-up'" data-testid="game-plan-move">
          {{ board.move < 0 ? '−' : '+' }}{{ pts(board.move) }} pts
        </span>
        <span v-if="board.adrMultiple !== null && plan.ctx.adr" class="gp-dim">
          Range {{ pts(board.rangeSoFar ?? 0) }} pts · {{ board.adrMultiple }}× a normal day ({{ Math.round(plan.ctx.adr) }} pts)
        </span>
      </section>

      <p class="gp-watch" data-testid="game-plan-watch">{{ board.watch }}</p>

      <section class="gp-list">
        <span class="gp-label">Open targets</span>
        <template v-for="r in board.above" :key="r.level.id">
          <game-plan-row :row="r" :open="openId === r.level.id" @toggle="toggleRow(r.level.id)" />
        </template>
        <div class="gp-now"><span>{{ fmt(price) }}</span></div>
        <template v-for="r in board.below" :key="r.level.id">
          <game-plan-row :row="r" :open="openId === r.level.id" @toggle="toggleRow(r.level.id)" />
        </template>
        <p v-if="!board.above.length && !board.below.length" class="gp-dim">No open targets near price.</p>
      </section>

      <section v-if="board.tally.length" class="gp-tally">
        <span class="gp-label">Who missed what</span>
        <div v-for="s in board.tally" :key="s.key" class="gp-tally-row" :class="{ 'gp-tally-row--live': s.live }">
          <span>{{ s.name }}<span v-if="s.live" class="gp-live-dot" aria-label="running now" /></span>
          <span class="gp-mono"><span class="gp-up">{{ s.hit }} ✓</span> · <span class="gp-down">{{ s.missed }} ✗</span></span>
        </div>
      </section>

      <section v-if="board.done.length" class="gp-done">
        <button class="gp-label gp-done-toggle" type="button" :aria-expanded="showDone" @click="showDone = !showDone">
          {{ showDone ? '▾' : '▸' }} Hit today ({{ board.done.length }})
        </button>
        <template v-if="showDone">
          <div v-for="r in board.done" :key="r.level.id" class="gp-done-row">
            <span class="gp-up">✓</span>
            <span class="gp-done-name">{{ r.level.label }}</span>
            <span class="gp-mono gp-dim">{{ clock(r.level.hitAt!) }}</span>
          </div>
        </template>
      </section>

      <game-plan-mini-chart v-if="live" :plan="plan" :board="board" :t="live.t" :price="live.price" />

      <p class="gp-foot">ES 2016–2025 stats. Odds, never trade calls. ↻ = a session missed it and it carried over.</p>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, type PropType } from 'vue';

import GamePlanMiniChart from '@/components/Chart/GamePlanMiniChart.vue';
import { useCandlesticksStore } from '@/stores/candlesticksStore';
import { useGamePlanStore } from '@/stores/gamePlanStore';
import { buildBoard, type BoardRow } from '@/utils/chart/gamePlan';

defineOptions({ name: 'GamePlanPanel' });

const store = useGamePlanStore();
const candles = useCandlesticksStore();
const plan = computed(() => store.plan);
const openId = ref<string | null>(null);
const showDone = ref(false);

// The candle store updates in place, so read its last bar on a short tick.
const tick = ref(0);
let timer: ReturnType<typeof setInterval> | null = null;
onMounted(() => { timer = setInterval(() => { tick.value++; }, 2000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });

const live = computed(() => {
  void tick.value;
  const p = plan.value;
  if (!p) return null;
  const bars = candles.data;
  const lastBar = bars.length ? bars[bars.length - 1] : null;
  let t = p.last?.t ?? p.start;
  let price = p.last?.close ?? NaN;
  if (lastBar && lastBar.timestamp_ms >= t && lastBar.timestamp_ms < p.end) {
    t = lastBar.timestamp_ms;
    price = Number(lastBar.close);
  }
  return Number.isFinite(price) ? { t, price } : null;
});
const price = computed(() => live.value?.price ?? 0);
const board = computed(() => (plan.value && live.value ? buildBoard(plan.value, live.value.t, live.value.price) : null));

const clockFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' });
const clock = (ms: number): string => clockFmt.format(new Date(ms));
const timeLabel = computed(() => (live.value ? `${plan.value?.label ?? ''} · ${clock(live.value.t)}` : ''));
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pts = (v: number): string => (Math.round(Math.abs(v) * 4) / 4).toLocaleString('en-US', { maximumFractionDigits: 2 });

function toggleRow(id: string): void {
  openId.value = openId.value === id ? null : id;
}

/** One target: name and odds (or "carried"); tap for the why and which sessions missed it. */
const GamePlanRow = defineComponent({
  name: 'GamePlanRow',
  props: { row: { type: Object as PropType<BoardRow>, required: true }, open: { type: Boolean, default: false } },
  emits: ['toggle'],
  setup(props, { emit }) {
    return () => {
      const { level, odds, distance, track } = props.row;
      const v = odds.value;
      const tone = odds.carried ? 'carried' : v === null ? 'none' : v >= 70 ? 'strong' : v >= 40 ? 'mid' : 'weak';
      const right = odds.carried ? '↻ carried' : v !== null ? `${v}%` : odds.note ? '6:30' : '';
      const missed = track.filter((s) => s.state === 'miss').map((s) => s.name);
      const carriedWhy = level.fromDay
        ? null
        : odds.carried && missed.length ? `${missed.join(' and ')} missed it, so it carried over.` : null;
      return h('div', { class: ['gp-row', { 'gp-row--open': props.open }] }, [
        h('button', { class: 'gp-row-main', type: 'button', 'aria-expanded': props.open, onClick: () => emit('toggle') }, [
          h('span', { class: 'gp-pip', style: { background: level.color } }),
          h('span', { class: 'gp-row-name' }, level.label),
          h('span', { class: 'gp-row-px' }, [fmt(level.price), h('small', `${distance >= 0 ? '+' : '−'}${pts(distance)}`)]),
          h('span', { class: ['gp-odds', `gp-odds--${tone}`] }, right),
        ]),
        props.open
          ? h('div', { class: 'gp-row-more' }, [
              h('div', { class: 'gp-track' }, [
                ...(level.fromDay ? [h('span', { class: 'gp-tk gp-tk--y' }, `${level.fromDay} ✗`)] : []),
                ...track.map((s) => h('span', { class: ['gp-tk', `gp-tk--${s.state}`] }, `${s.state === 'hit' ? '✓' : s.state === 'miss' ? '✗' : '●'} ${s.name}`)),
              ]),
              h('p', [level.why, odds.note, carriedWhy].filter(Boolean).join(' ')),
            ])
          : null,
      ]);
    };
  },
});
</script>

<style scoped>
.gp {
  width: 248px;
  flex: 0 0 248px;
  min-height: 0;
  overflow-y: auto;
  background: #131722;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #d7dbe3;
  font-size: 12px;
}
.gp-head { display: flex; align-items: baseline; gap: 8px; }
.gp-title { font-weight: 600; font-size: 13px; }
.gp-time { color: #8a919c; font-size: 11px; margin-left: auto; font-variant-numeric: tabular-nums; }
.gp-x { background: transparent; border: 0; color: #8a919c; font-size: 16px; line-height: 1; cursor: pointer; padding: 0 2px; }
.gp-x:hover { color: #d7dbe3; }
.gp-empty { color: #8a919c; margin: 0; }
.gp-day { display: flex; flex-direction: column; gap: 5px; }
.gp-chip { align-self: flex-start; border: 1px solid; border-radius: 999px; padding: 1px 9px; font-size: 11px; font-weight: 600; }
.gp-chip--trend { border-color: #d946ef; color: #e879f9; }
.gp-chip--either { border-color: #e9c46a; color: #e9c46a; }
.gp-chip--range { border-color: #4c9be8; color: #4c9be8; }
.gp-move { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; font-family: ui-monospace, Menlo, monospace; }
.gp-up { color: #2fb67c; }
.gp-down { color: #e5534b; }
.gp-dim { color: #8a919c; font-size: 11px; }
.gp-mono { font-family: ui-monospace, Menlo, monospace; font-size: 11px; }
.gp-watch { margin: 0; background: #181d2a; border-radius: 6px; padding: 8px 10px; line-height: 1.5; }
.gp-label { color: #5d6474; font-size: 11px; }
.gp-list, .gp-tally, .gp-done { display: flex; flex-direction: column; gap: 2px; }
.gp-now { position: relative; border-top: 1px dashed #e9c46a; margin: 8px 0; }
.gp-now span { position: absolute; right: 0; top: -8px; background: #131722; color: #e9c46a; padding-left: 4px; font-family: ui-monospace, Menlo, monospace; font-size: 11px; }
:deep(.gp-row-main) { all: unset; box-sizing: border-box; width: 100%; display: grid; grid-template-columns: 6px minmax(0, 1fr) auto auto; gap: 7px; align-items: center; padding: 4px 2px; border-radius: 4px; cursor: pointer; }
:deep(.gp-row-main:hover), :deep(.gp-row--open .gp-row-main) { background: #181d2a; }
:deep(.gp-row-main:focus-visible) { outline: 1px solid #4c9be8; }
:deep(.gp-pip) { width: 6px; height: 6px; border-radius: 2px; }
:deep(.gp-row-name) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:deep(.gp-row-px) { font-family: ui-monospace, Menlo, monospace; font-size: 11px; text-align: right; line-height: 1.15; }
:deep(.gp-row-px small) { display: block; color: #5d6474; font-size: 10px; }
:deep(.gp-odds) { font-family: ui-monospace, Menlo, monospace; font-size: 11px; min-width: 40px; text-align: right; color: #8a919c; }
:deep(.gp-odds--strong) { color: #2fb67c; }
:deep(.gp-odds--mid) { color: #e9c46a; }
:deep(.gp-odds--carried) { color: #b49af0; font-family: inherit; }
:deep(.gp-row-more) { padding: 2px 4px 6px 15px; color: #8a919c; font-size: 11px; line-height: 1.45; }
:deep(.gp-row-more p) { margin: 4px 0 0; }
:deep(.gp-track) { display: flex; flex-wrap: wrap; gap: 3px; }
:deep(.gp-tk) { border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 3px; padding: 0 4px; font-family: ui-monospace, Menlo, monospace; font-size: 10px; }
:deep(.gp-tk--miss) { color: #e5534b; border-color: rgba(229, 83, 75, 0.4); }
:deep(.gp-tk--hit) { color: #2fb67c; border-color: rgba(47, 182, 124, 0.45); }
:deep(.gp-tk--live) { color: #e9c46a; border-color: rgba(233, 196, 106, 0.45); }
:deep(.gp-tk--y) { color: #b49af0; border-color: rgba(180, 154, 240, 0.4); }
.gp-tally-row { display: flex; justify-content: space-between; padding: 2px 0; }
.gp-tally-row--live { color: #e9c46a; }
.gp-live-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #e9c46a; margin-left: 6px; vertical-align: middle; }
.gp-done-toggle { all: unset; cursor: pointer; color: #5d6474; font-size: 11px; }
.gp-done-row { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; gap: 6px; padding: 2px 0; }
.gp-done-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gp-foot { color: #5d6474; font-size: 10.5px; margin: 0; line-height: 1.4; }
</style>
