<template>
  <template v-if="view">
    <div
      class="aln-story"
      :class="`aln-story--${view.tone}`"
      data-testid="aln-story"
    >
      {{ view.sentence }}
    </div>

    <div class="aln-card" data-testid="aln-card">
      <button class="aln-card-head" type="button" @click="open = !open">
        <span class="aln-card-title">Walk-through</span>
        <span class="aln-card-toggle">{{ open ? '–' : '+' }}</span>
      </button>

      <template v-if="open">
        <ol class="aln-steps">
          <li
            v-for="step in view.steps"
            :key="step.key"
            :class="`aln-step--${step.state}`"
          >
            <span class="aln-step-dot" />{{ step.label }}
          </li>
        </ol>

        <div v-if="view.checks.length" class="aln-section">
          <div class="aln-section-title">What to look for</div>
          <div
            v-for="check in view.checks"
            :key="check.question"
            class="aln-check"
            :class="`aln-check--${check.state}`"
          >
            <span class="aln-check-mark">{{ mark(check.state) }}</span>
            <div>
              <div class="aln-check-q">{{ check.question }}</div>
              <div class="aln-check-a">{{ check.answer }}</div>
            </div>
          </div>
        </div>

        <div v-if="view.recent.length" class="aln-section">
          <div class="aln-section-title">Recent days</div>
          <div class="aln-recent">
            <span
              v-for="day in [...view.recent].reverse()"
              :key="day.ago"
              class="aln-recent-dot"
              :class="`aln-recent-dot--${day.kind}`"
              :title="day.text"
              @mouseenter="hovered = day.text"
              @mouseleave="hovered = null"
            />
          </div>
          <div class="aln-recent-text">
            {{ hovered ?? 'Filled = reached · hollow = not · square = no lean' }}
          </div>
        </div>

        <details v-if="view.details.length" class="aln-section aln-details">
          <summary>Details</summary>
          <div v-for="row in view.details" :key="row.label" class="aln-detail-row">
            <span>{{ row.label }}</span><span>{{ row.value }}</span>
          </div>
          <div class="aln-detail-note">From {{ source }}. Past behaviour, not a promise.</div>
        </details>
      </template>
    </div>
  </template>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

import { useIndicatorsStore } from "@/stores/indicatorsStore";
import type { IndicatorDataPoint } from "@/types/contracts";
import { buildGuideView, readGuideConfig, type GuideCheck } from "@/utils/chart/alnGuide";

defineOptions({ name: "AlnGuideOverlay" });

const props = defineProps<{ timeZone: string }>();

const indicatorsStore = useIndicatorsStore();
const open = ref(true);
const hovered = ref<string | null>(null);

const indicator = computed(() =>
  indicatorsStore.all.find((item) => readGuideConfig(item.info.guide) !== null) ?? null,
);

const source = computed(() => {
  const value = indicator.value?.info.guide?.source;
  return typeof value === "string" ? value : "past data";
});

const view = computed(() => {
  const item = indicator.value;
  if (!item) return null;
  const config = readGuideConfig(item.info.guide);
  if (!config) return null;
  void item.dataVersion;
  const points: IndicatorDataPoint[] = item.data.slice(-2000);
  const live = item.lastLivePoint;
  const last = points[points.length - 1];
  if (live && (!last || Number(live.timestamp_ms) > Number(last.timestamp_ms))) points.push(live);
  else if (live && last && Number(live.timestamp_ms) === Number(last.timestamp_ms)) points[points.length - 1] = live;
  return buildGuideView(points, config, props.timeZone);
});

function mark(state: GuideCheck["state"]): string {
  return state === "yes" ? "✓" : state === "no" ? "✕" : "•";
}
</script>

<style scoped>
.aln-story {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  max-width: min(620px, 60%);
  padding: 8px 14px;
  border-left: 3px solid #e9c46a;
  border-radius: 6px;
  background: rgba(19, 23, 34, 0.88);
  color: #e6e6e6;
  font-size: 13px;
  line-height: 1.4;
  pointer-events: none;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}

.aln-story--done { border-left-color: #3fb950; }
.aln-story--changed { border-left-color: #56606b; color: #b7bec7; }
.aln-story--waiting { border-left-color: #5b7cfa; }

.aln-card {
  position: absolute;
  top: 56px;
  right: 72px;
  z-index: 5;
  width: 250px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(19, 23, 34, 0.92);
  color: #d1d4dc;
  font-size: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.aln-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.aln-card-title { font-weight: 600; letter-spacing: 0.02em; }
.aln-card-toggle { color: #8a919c; font-size: 14px; }

.aln-steps {
  display: flex;
  justify-content: space-between;
  margin: 0;
  padding: 0 12px 8px;
  list-style: none;
  color: #5d6570;
  font-size: 11px;
}

.aln-steps li { display: flex; align-items: center; gap: 4px; }
.aln-step-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.aln-step--done { color: #8a919c; }
.aln-step--current { color: #e9c46a; font-weight: 600; }

.aln-section { padding: 8px 12px; border-top: 1px solid rgba(255, 255, 255, 0.06); }
.aln-section-title { margin-bottom: 6px; color: #8a919c; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }

.aln-check { display: flex; gap: 8px; margin-bottom: 6px; }
.aln-check-mark { width: 14px; flex: none; text-align: center; color: #8a919c; }
.aln-check--yes .aln-check-mark { color: #3fb950; }
.aln-check--no .aln-check-mark { color: #e0574a; }
.aln-check-q { color: #e6e6e6; }
.aln-check-a { color: #8a919c; }

.aln-recent { display: flex; gap: 6px; }
.aln-recent-dot { width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid #e9c46a; cursor: default; }
.aln-recent-dot--hit { background: #e9c46a; }
.aln-recent-dot--flat { border-radius: 2px; border-color: #56606b; background: #56606b; }
.aln-recent-text { min-height: 30px; margin-top: 6px; color: #8a919c; line-height: 1.35; }

.aln-details summary { color: #8a919c; cursor: pointer; }
.aln-detail-row { display: flex; justify-content: space-between; padding: 2px 0; }
.aln-detail-note { margin-top: 4px; color: #5d6570; font-size: 11px; }
</style>
