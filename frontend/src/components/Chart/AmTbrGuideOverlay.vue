<template>
  <div v-if="view" class="tbrg" :class="`tbrg--${view.tone}`" data-testid="am-tbr-guide">
    <div class="tbrg-steps">
      <span v-for="step in view.steps" :key="step.label" :class="`tbrg-step--${step.state}`">
        <i class="tbrg-dot" />{{ step.label }}
      </span>
    </div>
    <div class="tbrg-sentence">{{ view.sentence }}</div>
    <div class="tbrg-detail">{{ view.detail }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { useIndicatorsStore } from "@/stores/indicatorsStore";
import type { JsonObject } from "@/types/contracts";
import { activeTbrSession, buildTbrGuideView, TBR_SESSION_START_HOUR } from "@/utils/chart/tbrGuide";

defineOptions({ name: "AmTbrGuideOverlay" });

const props = defineProps<{ timeZone: string }>();
const indicatorsStore = useIndicatorsStore();

const indicator = computed(() =>
  indicatorsStore.all.find((item) => {
    const kind = (item.info.guide as JsonObject | undefined)?.kind;
    return kind === "tbr_am" || kind === "tbr";
  }) ?? null,
);

const view = computed(() => {
  const item = indicator.value;
  if (!item) return null;
  void item.dataVersion;
  const guide = (item.info.guide ?? {}) as JsonObject;
  if (guide.kind === "tbr_am") {
    const point = item.lastLivePoint ?? item.data[item.data.length - 1] ?? null;
    const rates = (guide.rates ?? {}) as unknown as Record<string, [number, number]>;
    return buildTbrGuideView(point, rates, props.timeZone);
  }
  // ALN TBR: walk through whichever chosen session is running (or ran last).
  const all = (guide.sessions ?? []) as unknown as { key: string; label: string; rates?: Record<string, [number, number]> }[];
  const param = item.parameters?.sessions as { value?: unknown; default?: unknown } | undefined;
  const chosen = String(param?.value ?? param?.default ?? "").toLowerCase().split(/[,;]/).map((s) => s.trim()).filter(Boolean);
  const sessions = all.filter((s) => chosen.length === 0 || chosen.includes(s.key));
  const points = item.lastLivePoint ? [...item.data, item.lastLivePoint] : item.data;
  const active = activeTbrSession(points, sessions);
  if (!active) return null;
  const rates = sessions.find((s) => s.key === active.key)?.rates ?? {};
  return buildTbrGuideView(active.point, rates, props.timeZone, {
    label: `${active.label} TBR`,
    startHour: TBR_SESSION_START_HOUR[active.key],
  });
});
</script>

<style scoped>
.tbrg {
  position: absolute;
  top: 56px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  max-width: min(640px, 64%);
  padding: 8px 14px;
  border-left: 3px solid #5b7cfa;
  border-radius: 6px;
  background: rgba(19, 23, 34, 0.9);
  color: #e6e6e6;
  font-size: 13px;
  line-height: 1.4;
  pointer-events: none;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}

.tbrg--live { border-left-color: #e9c46a; }
.tbrg--warn { border-left-color: #e0574a; }
.tbrg--done { border-left-color: #3fb950; }
.tbrg-steps { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 4px; color: #5d6570; font-size: 11px; }
.tbrg-steps span { display: inline-flex; align-items: center; gap: 4px; }
.tbrg-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.tbrg-step--done { color: #8a919c; }
.tbrg-step--current { color: #e9c46a; font-weight: 600; }
.tbrg-detail { margin-top: 2px; color: #9aa4b2; font-size: 12px; }
</style>
