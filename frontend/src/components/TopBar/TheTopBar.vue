<template>
  <div id="wrapper-select">
    <n-button primary round data-testid="topbar-symbol" @click="openModal('symbolSearch')">
      {{ remote ? (remote.symbol ?? '—') : currentSymbol }}
    </n-button>

    <TimeframeDropdown
      :remote-value="remote ? remote.timeframe : undefined"
      @remote-select="(value: string) => emit('remote-timeframe', value)"
    />

    <n-button round data-testid="topbar-indicator" @click="openModal('indicatorSearch')">Indicator</n-button>

    <span v-if="remote" class="active-chart-note" data-testid="active-chart-note">Right chart</span>

    <div class="chart-interaction-controls" role="group" aria-label="Chart interaction mode">
      <n-button
        size="small"
        round
        class="position-button position-button--long"
        :class="{ 'position-button--active': isChartInteractionModeSelected('long') }"
        data-testid="chart-mode-long"
        title="Long position: click the chart at your entry"
        :aria-pressed="isChartInteractionModeSelected('long')"
        @click="toggleMode('long')"
      >Long</n-button>
      <n-button
        size="small"
        round
        class="position-button position-button--short"
        :class="{ 'position-button--active': isChartInteractionModeSelected('short') }"
        data-testid="chart-mode-short"
        title="Short position: click the chart at your entry"
        :aria-pressed="isChartInteractionModeSelected('short')"
        @click="toggleMode('short')"
      >Short</n-button>
      <n-button
        size="small"
        round
        class="position-button position-button--retrace"
        :class="{ 'position-button--active': isChartInteractionModeSelected('retrace') }"
        data-testid="chart-mode-retrace"
        title="Retrace: click the leg's start, then its end (snaps to the candle's high or low)"
        :aria-pressed="isChartInteractionModeSelected('retrace')"
        @click="toggleMode('retrace')"
      >Retrace</n-button>
      <n-button
        circle
        class="chart-interaction-mode-button"
        :class="{
          'chart-interaction-mode-button--active': isChartInteractionModeSelected('pan'),
        }"
        data-testid="chart-interaction-mode-pan"
        aria-label="Pan mode"
        :aria-pressed="isChartInteractionModeSelected('pan')"
        @click="selectChartInteractionMode('pan')"
      >
        <template #icon>
          <n-icon
            size="20"
            :color="chartInteractionModeIconColor('pan')"
          >
            <HandRightOutline />
          </n-icon>
        </template>
      </n-button>

      <n-button
        circle
        class="chart-interaction-mode-button"
        :class="{
          'chart-interaction-mode-button--active': isChartInteractionModeSelected('measure'),
        }"
        data-testid="chart-interaction-mode-measure"
        aria-label="Measure mode"
        :aria-pressed="isChartInteractionModeSelected('measure')"
        @click="selectChartInteractionMode('measure')"
      >
        <template #icon>
          <n-icon
            size="20"
            :color="chartInteractionModeIconColor('measure')"
          >
            <ResizeOutline />
          </n-icon>
        </template>
      </n-button>
    </div>

    <div v-if="showLayout" class="chart-layout-controls" role="group" aria-label="Chart layout">
      <n-button
        size="small"
        round
        :type="chartLayout === 'single' ? 'primary' : 'default'"
        :secondary="chartLayout !== 'single'"
        data-testid="chart-layout-single"
        :aria-pressed="chartLayout === 'single'"
        @click="emit('update:chartLayout', 'single')"
      >1 chart</n-button>
      <n-button
        size="small"
        round
        :type="chartLayout === 'split' ? 'primary' : 'default'"
        :secondary="chartLayout !== 'split'"
        data-testid="chart-layout-split"
        :aria-pressed="chartLayout === 'split'"
        @click="emit('update:chartLayout', 'split')"
      >2 charts</n-button>
    </div>

    <TopBarModals v-if="!remote" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NIcon } from 'naive-ui';

import {
  DEFAULT_CHART_INTERACTION_MODE,
  type ChartInteractionMode,
} from '@/components/Chart/chartInteractionMode';
import TimeframeDropdown from '@/components/TopBar/TimeframeDropdown.vue';
import TopBarModals from '@/components/TopBar/Modals/TopBarModals.vue';
import { HandRightOutline, ResizeOutline } from '@/icons';
import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useModalStore } from '@/stores/modalStore';
import type { ChartLayout } from '@/utils/chartPane';

defineOptions({
  name: 'TheTopBar',
});

const props = withDefaults(defineProps<{
  chartInteractionMode?: ChartInteractionMode;
  chartLayout?: ChartLayout;
  showLayout?: boolean;
  /** The active chart is the second one: its symbol and timeframe, and actions go to it. */
  remote?: { symbol: string | null; timeframe: string } | null;
}>(), {
  chartInteractionMode: DEFAULT_CHART_INTERACTION_MODE,
  chartLayout: 'single',
  showLayout: false,
  remote: null,
});

const emit = defineEmits<{
  'update:chartInteractionMode': [mode: ChartInteractionMode];
  'update:chartLayout': [layout: ChartLayout];
  'remote-modal': [name: string];
  'remote-timeframe': [value: string];
}>();

function openModal(name: string): void {
  if (props.remote) emit('remote-modal', name);
  else modalStore.openModal(name);
}

const currentMarketStore = useCurrentMarketStore();
const modalStore = useModalStore();
const currentSymbol = computed(() => currentMarketStore.symbol);
const selectedChartInteractionModeColor = '#7fe7c4';

function isChartInteractionModeSelected(mode: ChartInteractionMode): boolean {
  return props.chartInteractionMode === mode;
}

function chartInteractionModeIconColor(mode: ChartInteractionMode): string | undefined {
  return isChartInteractionModeSelected(mode) ? selectedChartInteractionModeColor : undefined;
}

function selectChartInteractionMode(mode: ChartInteractionMode): void {
  emit('update:chartInteractionMode', mode);
}

function toggleMode(mode: ChartInteractionMode): void {
  emit('update:chartInteractionMode', props.chartInteractionMode === mode ? 'pan' : mode);
}
</script>

<style scoped>
#wrapper-select {
  flex-shrink: 0;
  margin-bottom: 20px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.chart-interaction-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.position-button--long { color: #3fb950; }
.position-button--short { color: #e0574a; }
.position-button--active.position-button--long { background: rgba(63, 185, 80, 0.2); }
.position-button--active.position-button--short { background: rgba(224, 87, 74, 0.2); }
.position-button--retrace { color: #e9c46a; }
.position-button--active.position-button--retrace { background: rgba(233, 196, 106, 0.2); }

.active-chart-note {
  align-self: center;
  font-size: 12px;
  color: #7fe7c4;
}

.chart-layout-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.chart-interaction-mode-button--active :deep(.n-button__state-border) {
  border: var(--n-border-hover);
}

.chart-interaction-mode-button--active :deep(.n-button__content) {
  color: #7fe7c4;
}
</style>
