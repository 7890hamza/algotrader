<template>
  <main class="chart-workspace" :class="{ 'chart-workspace--split': isSplit }">
    <section class="chart-pane">
      <TheTopBar
        v-model:chart-interaction-mode="chartInteractionMode"
        :chart-layout="chartLayout"
        :show-layout="!isSecondPane"
        @update:chart-layout="setChartLayout"
      />
      <ChartArea
        id="chart-area"
        ref="chartArea"
        :interaction-mode="chartInteractionMode"
      />
    </section>
    <iframe
      v-if="isSplit"
      class="chart-pane chart-pane--second"
      :src="secondSrc"
      title="Second chart"
      data-testid="second-chart"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import ChartArea from '@/components/Chart/ChartArea.vue';
import {
  DEFAULT_CHART_INTERACTION_MODE,
  type ChartInteractionMode,
} from '@/components/Chart/chartInteractionMode';
import TheTopBar from '@/components/TopBar/TheTopBar.vue';
import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useMarketsStore } from '@/stores/marketsStore';
import {
  CHART_LAYOUT_KEY,
  IS_SECOND_PANE,
  secondPaneUrl,
  type ChartLayout,
} from '@/utils/chartPane';

defineOptions({
  name: 'ChartView',
});

const marketsStore = useMarketsStore();
const currentMarketStore = useCurrentMarketStore();
const chartInteractionMode = ref<ChartInteractionMode>(DEFAULT_CHART_INTERACTION_MODE);
const isSecondPane = IS_SECOND_PANE;
const secondSrc = secondPaneUrl();

function readLayout(): ChartLayout {
  try {
    return localStorage.getItem(CHART_LAYOUT_KEY) === 'split' ? 'split' : 'single';
  } catch {
    return 'single';
  }
}

const chartLayout = ref<ChartLayout>(isSecondPane ? 'single' : readLayout());
const isSplit = computed(() => !isSecondPane && chartLayout.value === 'split');

function setChartLayout(layout: ChartLayout): void {
  chartLayout.value = layout;
  try {
    localStorage.setItem(CHART_LAYOUT_KEY, layout);
  } catch {
    // Layout is a convenience; ignore storage failures.
  }
}

async function fetchMarketsAndInitCurrent(): Promise<void> {
  await marketsStore.fetch();

  if (marketsStore.all.length === 0) {
    return;
  }

  if (currentMarketStore.isValid(marketsStore.all)) {
    return;
  }

  currentMarketStore.setMarket(marketsStore.all[0]);
}

async function initializeChartView(): Promise<void> {
  await fetchMarketsAndInitCurrent();
}

void initializeChartView();
</script>

<style scoped>
.chart-workspace {
  display: flex;
  flex-direction: row;
  gap: 8px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.chart-pane {
  display: flex;
  flex-direction: column;
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
}

.chart-pane--second {
  border: 0;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  padding-left: 8px;
  background: transparent;
}

#chart-area {
  flex: 1;
  min-height: 0;
}
</style>
