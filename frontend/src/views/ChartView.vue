<template>
  <main class="chart-workspace">
    <TheTopBar
      v-if="!isSecondPane"
      v-model:chart-interaction-mode="chartInteractionMode"
      :chart-layout="chartLayout"
      :show-layout="true"
      :remote="activePane !== '1' && isMulti ? (paneStates[activePane] ?? null) : null"
      @update:chart-layout="setChartLayout"
      @remote-modal="(name: string) => sendToActive({ type: 'open-modal', name })"
      @remote-timeframe="(value: string) => sendToActive({ type: 'set-timeframe', value })"
    />
    <TopBarModals v-else />
    <div class="chart-panes">
      <div class="chart-grid" :class="`chart-grid--${isSecondPane ? 'single' : chartLayout}`">
      <section
        class="chart-pane"
        :class="{ 'chart-pane--active': isMulti && activePane === '1' }"
        data-testid="first-chart"
        @pointerdown.capture="activate"
      >
        <div v-if="isMulti || isSecondPane" class="pane-label" data-testid="pane-label">
          <span>{{ currentMarketStore.symbol ?? '—' }}</span>
          <span class="pane-label__tf">{{ currentTimeframeStore.value }}</span>
        </div>
        <ChartArea
          id="chart-area"
          ref="chartArea"
          :interaction-mode="chartInteractionMode"
          @placed="onPlaced"
        />
      </section>
      <iframe
        v-for="pane in extraPanes"
        :key="pane"
        :ref="(el) => setFrame(pane, el)"
        class="chart-pane chart-pane--second"
        :class="{ 'chart-pane--active': activePane === pane }"
        :src="paneSrc(pane)"
        :title="`Chart ${pane}`"
        :data-testid="pane === '2' ? 'second-chart' : `chart-${pane}`"
      />
      </div>
      <GamePlanPanel v-if="!isSecondPane && gamePlanStore.visible" />
      <MemoryDomPanel v-if="!isSecondPane && domStore.visible" />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChartArea from '@/components/Chart/ChartArea.vue';
import GamePlanPanel from '@/components/Chart/GamePlanPanel.vue';
import MemoryDomPanel from '@/components/Chart/MemoryDomPanel.vue';
import {
  CHART_INTERACTION_MODES,
  DEFAULT_CHART_INTERACTION_MODE,
  type ChartInteractionMode,
} from '@/components/Chart/chartInteractionMode';
import TheTopBar from '@/components/TopBar/TheTopBar.vue';
import TopBarModals from '@/components/TopBar/Modals/TopBarModals.vue';
import { useCurrentMarketStore } from '@/stores/currentMarketStore';
import { useCurrentTimeframeStore } from '@/stores/currentTimeframeStore';
import { useDomStore } from '@/stores/domStore';
import { useGamePlanStore } from '@/stores/gamePlanStore';
import { useMarketsStore } from '@/stores/marketsStore';
import { STORAGE_KEYS } from '@/utils/localStorage';
import { useModalStore } from '@/stores/modalStore';
import { isTimeframeCode } from '@/types/contracts';
import {
  CHART_LAYOUT_KEY,
  CHART_LAYOUTS,
  EXTRA_PANES,
  IS_SECOND_PANE,
  PANE_DEFAULT_SYMBOL,
  PANE_SYMBOL,
  paneHasOwnSymbol,
  paneUrl,
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
const gamePlanStore = useGamePlanStore();
const domStore = useDomStore();
if (!IS_SECOND_PANE) watch(() => currentMarketStore.symbol, (s) => gamePlanStore.setSymbol(s ?? null), { immediate: true });
const chartInteractionMode = ref<ChartInteractionMode>(DEFAULT_CHART_INTERACTION_MODE);
const isSecondPane = IS_SECOND_PANE;
const frames: Record<string, HTMLIFrameElement | null> = {};
const activePane = ref<string>('1');
const paneStates = ref<Record<string, { symbol: string | null; timeframe: string }>>({});

function readLayout(): ChartLayout {
  try {
    const saved = localStorage.getItem(CHART_LAYOUT_KEY);
    return (CHART_LAYOUTS as readonly string[]).includes(saved ?? '') ? (saved as ChartLayout) : 'single';
  } catch {
    return 'single';
  }
}

const chartLayout = ref<ChartLayout>(isSecondPane ? 'single' : readLayout());
const isMulti = computed(() => !isSecondPane && chartLayout.value !== 'single');
const extraPanes = computed(() => (isSecondPane ? [] : EXTRA_PANES[chartLayout.value]));

function paneSrc(pane: string): string {
  return paneUrl(pane, chartLayout.value === 'quad' ? PANE_DEFAULT_SYMBOL[pane] : undefined);
}

function setFrame(pane: string, el: unknown): void {
  frames[pane] = el instanceof HTMLIFrameElement ? el : null;
}

function setChartLayout(layout: ChartLayout): void {
  chartLayout.value = layout;
  if (!EXTRA_PANES[layout].includes(activePane.value)) activePane.value = '1';
  try {
    localStorage.setItem(CHART_LAYOUT_KEY, layout);
  } catch {
    // Layout is a convenience; ignore storage failures.
  }
}

function sendToActive(message: PaneMessage): void {
  postPaneMessage(frames[activePane.value]?.contentWindow, message);
}

function sendToAll(message: PaneMessage): void {
  for (const pane of extraPanes.value) postPaneMessage(frames[pane]?.contentWindow, message);
}

function paneOf(source: MessageEventSource | null): string | null {
  return extraPanes.value.find((pane) => frames[pane]?.contentWindow === source) ?? null;
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

/** A plan was placed: go back to pan (and tell the main page when this is the second chart). */
function onPlaced(): void {
  chartInteractionMode.value = 'pan';
  if (isSecondPane) postPaneMessage(window.parent, { type: 'placed' });
}

function onMessage(event: MessageEvent): void {
  const message = readPaneMessage(event);
  if (!message) return;
  if (!isSecondPane) {
    const pane = paneOf(event.source);
    if (!pane) return;
    if (message.type === 'activate') activePane.value = pane;
    if (message.type === 'placed') chartInteractionMode.value = 'pan';
    if (message.type === 'state') {
      paneStates.value = { ...paneStates.value, [pane]: { symbol: message.symbol, timeframe: message.timeframe } };
      postPaneMessage(frames[pane]?.contentWindow, { type: 'set-interaction-mode', mode: chartInteractionMode.value });
    }
    return;
  }
  if (message.type === 'open-modal') modalStore.openModal(message.name);
  if (message.type === 'set-timeframe' && isTimeframeCode(message.value)) {
    currentTimeframeStore.setCurrentTimeframe({ label: message.value, value: message.value });
  }
  if (message.type === 'set-interaction-mode' && (CHART_INTERACTION_MODES as readonly string[]).includes(message.mode)) {
    chartInteractionMode.value = message.mode as ChartInteractionMode;
  }
}

watch(chartInteractionMode, (mode) => {
  if (isMulti.value) sendToAll({ type: 'set-interaction-mode', mode });
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

  // A new chart in the 4-chart grid opens on its own market (NQ, MES, MNQ) when that market exists.
  const paneSymbol = PANE_SYMBOL?.toUpperCase();
  if (isSecondPane && paneSymbol && !paneHasOwnSymbol(STORAGE_KEYS.CURRENT_MARKET)) {
    const wanted = marketsStore.all.find((m) => m.symbol.toUpperCase() === paneSymbol);
    if (wanted) {
      currentMarketStore.setMarket(wanted);
      return;
    }
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

.chart-grid {
  display: grid;
  flex: 1;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.chart-grid--split {
  grid-template-columns: 1fr 1fr;
}

.chart-grid--quad {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
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
