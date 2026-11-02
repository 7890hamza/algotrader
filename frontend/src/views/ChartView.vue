<template>
  <main class="chart-workspace">
    <TheTopBar
      v-if="!isSecondPane"
      v-model:chart-interaction-mode="chartInteractionMode"
      :chart-layout="chartLayout"
      :show-layout="true"
      :remote="activePane === '2' && isSplit ? secondState : null"
      @update:chart-layout="setChartLayout"
      @remote-modal="(name: string) => sendToSecond({ type: 'open-modal', name })"
      @remote-timeframe="(value: string) => sendToSecond({ type: 'set-timeframe', value })"
    />
    <TopBarModals v-else />
    <div class="chart-panes">
      <section
        class="chart-pane"
        :class="{ 'chart-pane--active': isSplit && activePane === '1' }"
        data-testid="first-chart"
        @pointerdown.capture="activate"
      >
        <div v-if="isSplit || isSecondPane" class="pane-label" data-testid="pane-label">
          <span>{{ currentMarketStore.symbol ?? '—' }}</span>
          <span class="pane-label__tf">{{ currentTimeframeStore.value }}</span>
        </div>
        <ChartArea
          id="chart-area"
          ref="chartArea"
          :interaction-mode="chartInteractionMode"
        />
      </section>
      <iframe
        v-if="isSplit"
        ref="secondFrame"
        class="chart-pane chart-pane--second"
        :class="{ 'chart-pane--active': activePane === '2' }"
        :src="secondSrc"
        title="Second chart"
        data-testid="second-chart"
      />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChartArea from '@/components/Chart/ChartArea.vue';
import {
  DEFAULT_CHART_INTERACTION_MODE,
  type ChartInteractionMode,
} from '@/components/Chart/chartInteractionMode';
import TheTopBar from '@/components/TopBar/TheTopBar.vue';
import TopBarModals from '@/components/TopBar/Modals/TopBarModals.vue';
import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useCurrentTimeframeStore } from '@/stores/currentTimeframeStore';
import { useMarketsStore } from '@/stores/marketsStore';
import { useModalStore } from '@/stores/modalStore';
import { isTimeframeCode } from '@/types/contracts';
import {
  CHART_LAYOUT_KEY,
  IS_SECOND_PANE,
  secondPaneUrl,
  type ChartLayout,
} from '@/utils/chartPane';
import { postPaneMessage, readPaneMessage, type PaneMessage } from '@/utils/paneBridge';

defineOptions({
  name: 'ChartView',
});

const marketsStore = useMarketsStore();
const currentMarketStore = useCurrentMarketStore();
const currentTimeframeStore = useCurrentTimeframeStore();
const modalStore = useModalStore();
const chartInteractionMode = ref<ChartInteractionMode>(DEFAULT_CHART_INTERACTION_MODE);
const isSecondPane = IS_SECOND_PANE;
const secondSrc = secondPaneUrl();
const secondFrame = ref<HTMLIFrameElement | null>(null);
const activePane = ref<'1' | '2'>('1');
const secondState = ref<{ symbol: string | null; timeframe: string }>({ symbol: null, timeframe: '' });

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
  if (layout === 'single') activePane.value = '1';
  try {
    localStorage.setItem(CHART_LAYOUT_KEY, layout);
  } catch {
    // Layout is a convenience; ignore storage failures.
  }
}

function sendToSecond(message: PaneMessage): void {
  postPaneMessage(secondFrame.value?.contentWindow, message);
}

/** A click on this chart makes it the one the top bar works on. */
function activate(): void {
  if (isSecondPane) postPaneMessage(window.parent, { type: 'activate' });
  else activePane.value = '1';
}

function reportState(): void {
  if (!isSecondPane) return;
  postPaneMessage(window.parent, {
    type: 'state',
    symbol: currentMarketStore.symbol,
    timeframe: currentTimeframeStore.value,
  });
}

function onMessage(event: MessageEvent): void {
  const message = readPaneMessage(event);
  if (!message) return;
  if (!isSecondPane) {
    if (message.type === 'activate') activePane.value = '2';
    if (message.type === 'state') {
      secondState.value = { symbol: message.symbol, timeframe: message.timeframe };
      sendToSecond({ type: 'set-interaction-mode', mode: chartInteractionMode.value });
    }
    return;
  }
  if (message.type === 'open-modal') modalStore.openModal(message.name);
  if (message.type === 'set-timeframe' && isTimeframeCode(message.value)) {
    currentTimeframeStore.setCurrentTimeframe({ label: message.value, value: message.value });
  }
  if (message.type === 'set-interaction-mode' && (message.mode === 'pan' || message.mode === 'measure')) {
    chartInteractionMode.value = message.mode;
  }
}

watch(chartInteractionMode, (mode) => {
  if (isSplit.value) sendToSecond({ type: 'set-interaction-mode', mode });
});
watch(() => [currentMarketStore.symbol, currentTimeframeStore.value], reportState);

onMounted(() => {
  window.addEventListener('message', onMessage);
  reportState();
});
onBeforeUnmount(() => window.removeEventListener('message', onMessage));

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
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.chart-panes {
  display: flex;
  flex: 1;
  gap: 8px;
  min-height: 0;
}

.chart-pane {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  border: 1px solid transparent;
  border-radius: 6px;
}

.chart-pane--second {
  border-color: rgba(255, 255, 255, 0.08);
  background: transparent;
}

.chart-pane--active {
  border-color: rgba(127, 231, 196, 0.55);
}

.pane-label {
  position: absolute;
  top: 6px;
  right: 76px;
  z-index: 6;
  pointer-events: none;
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(19, 23, 34, 0.75);
  font-size: 12px;
  font-weight: 600;
  color: #d1d4dc;
}

.pane-label__tf {
  color: #8a919c;
  font-weight: 500;
}

#chart-area {
  flex: 1;
  min-height: 0;
}
</style>
