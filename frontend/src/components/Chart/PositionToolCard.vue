<template>
  <div class="ptc" :class="`ptc--${state.side}`" data-testid="position-tool-card">
    <div class="ptc-row ptc-head">
      <span class="ptc-side">{{ state.side === 'long' ? 'Long' : 'Short' }}</span>
      <button class="ptc-btn" type="button" title="Switch long / short" @click="$emit('flip')">⇅</button>
      <span class="ptc-qty">
        <button class="ptc-btn" type="button" aria-label="Fewer contracts" @click="$emit('qty', state.qty - 1)">−</button>
        <span>{{ state.qty }}</span>
        <button class="ptc-btn" type="button" aria-label="More contracts" @click="$emit('qty', state.qty + 1)">+</button>
      </span>
      <button class="ptc-btn ptc-close" type="button" aria-label="Remove" @click="$emit('remove')">×</button>
    </div>
    <template v-if="model.valid">
      <div class="ptc-row"><span>Risk</span><b class="ptc-loss">{{ money(-model.risk.money) }}</b><span class="ptc-dim">{{ fmt(model.risk.points) }} pts · {{ model.risk.ticks }} ticks</span></div>
      <div class="ptc-row"><span>Reward</span><b class="ptc-win">{{ money(model.reward.money) }}</b><span class="ptc-dim">{{ fmt(model.reward.points) }} pts · {{ model.reward.ticks }} ticks</span></div>
      <div class="ptc-row"><span>R:R</span><b>{{ model.rr.toFixed(2) }}</b><span class="ptc-dim">break-even win rate {{ breakEven }}%</span></div>
    </template>
    <div v-else class="ptc-row ptc-loss">Drag the stop and target to opposite sides of the entry.</div>
    <div class="ptc-row ptc-dim ptc-spec">
      <span>1 pt =</span>
      <input
        :value="model.pointValue.toFixed(2)"
        type="number"
        min="0"
        step="0.01"
        aria-label="Money per point"
        @change="onPointValue"
      >
      <span>{{ spec.currency }} · {{ sourceLabel }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

import type { ContractSpec } from '@/utils/chart/contractSpecs';
import { formatMoney, type PositionModel, type PositionToolState } from '@/utils/chart/positionTool';

defineOptions({ name: 'PositionToolCard' });

const props = defineProps<{ state: PositionToolState; model: PositionModel; spec: ContractSpec }>();
const emit = defineEmits<{ flip: []; remove: []; qty: [qty: number]; 'point-value': [value: number | null] }>();

const money = (v: number): string => formatMoney(v, props.spec.currency);
const fmt = (v: number): string => v.toFixed(props.model.decimals);
const breakEven = computed(() => (100 / (1 + props.model.rr)).toFixed(0));
const sourceLabel = computed(() => ({ mt5: 'from MT5', table: 'contract table', custom: 'your value', guess: 'guess, set it' })[props.spec.source]);

function onPointValue(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  emit('point-value', Number.isFinite(value) && value > 0 ? value : null);
}
</script>

<style scoped>
.ptc {
  position: absolute;
  bottom: 44px;
  left: 10px;
  z-index: 7;
  min-width: 250px;
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid #3fb950;
  background: rgba(19, 23, 34, 0.92);
  color: #d1d4dc;
  font-size: 12px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ptc--short { border-left-color: #e0574a; }
.ptc-row { display: flex; align-items: center; gap: 8px; font-variant-numeric: tabular-nums; }
.ptc-row > span:first-child { min-width: 44px; color: #8a919c; }
.ptc-head { justify-content: space-between; }
.ptc-side { font-weight: 600; color: #e6e6e6 !important; }
.ptc-qty { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; }
.ptc-btn { background: transparent; border: 1px solid rgba(255, 255, 255, 0.15); color: #d1d4dc; border-radius: 4px; width: 22px; height: 22px; cursor: pointer; line-height: 1; }
.ptc-btn:hover { border-color: rgba(255, 255, 255, 0.4); }
.ptc-close { border: 0; font-size: 16px; }
.ptc-win { color: #3fb950; }
.ptc-loss { color: #e0574a; }
.ptc-dim { color: #8a919c; font-size: 11px; }
.ptc-spec input { width: 70px; background: transparent; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 4px; color: #d1d4dc; padding: 1px 4px; font-size: 11px; }
</style>
