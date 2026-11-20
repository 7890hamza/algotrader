<template>
  <div v-if="replay.active || replay.pickerOpen" class="replay-bar" data-testid="replay-bar">
    <template v-if="!replay.active">
      <span class="title">Replay from</span>
      <input id="replay-date" v-model="pickDay" type="date" :max="today" aria-label="Day to replay">
      <button type="button" class="go" :disabled="!pickDay" @click="start">Start replay</button>
      <button type="button" aria-label="Close" @click="replay.pickerOpen = false">✕</button>
    </template>
    <template v-else>
      <span class="title">Replay</span>
      <span class="when">{{ cursorText }}</span>
      <button type="button" aria-label="Back one bar" @click="replay.step(-1)">◀</button>
      <button type="button" class="go" :aria-label="replay.playing ? 'Pause' : 'Play'" @click="replay.setPlaying(!replay.playing)">{{ replay.playing ? '❚❚ Pause' : '▶ Play' }}</button>
      <button type="button" aria-label="Forward one bar" @click="replay.step(1)">▶|</button>
      <button type="button" @click="replay.jump(3_600_000)">+1 hour</button>
      <button type="button" @click="replay.jump(86_400_000)">+1 day</button>
      <select id="replay-speed" v-model="speed" aria-label="Speed">
        <option value="1000">Slow</option>
        <option value="250">Normal</option>
        <option value="60">Fast</option>
        <option value="15">Fastest</option>
      </select>
      <input id="replay-jump" v-model="pickDay" type="date" :max="today" aria-label="Replay another day" @change="start">
      <button type="button" class="exit" @click="exit">Back to live</button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

import { useReplayStore } from '@/stores/replayStore';
import { DEFAULT_CHART_TIME_ZONE } from '@/utils/chart/chartTimeZone';
import { cmeDayStartMs, REPLAY_START_MS, replayUrl } from '@/utils/replay';

defineOptions({ name: 'ReplayBar' });

const replay = useReplayStore();
const ny = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', ...opts });
const today = ny({ year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const pickDay = ref<string>(REPLAY_START_MS ? ny({ year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(REPLAY_START_MS + 6 * 3_600_000)) : '');
const speed = computed({
  get: () => String(replay.msPerBar),
  set: (v: string) => replay.setSpeed(Number(v)),
});
const cursorText = computed(() => (Number.isFinite(replay.cursorMs)
  ? new Intl.DateTimeFormat('en-US', { timeZone: DEFAULT_CHART_TIME_ZONE, timeZoneName: 'short', weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(replay.cursorMs))
  : ''));

function start(): void {
  if (!pickDay.value) return;
  location.href = replayUrl(cmeDayStartMs(pickDay.value));
}
function exit(): void {
  location.href = replayUrl(null);
}
</script>

<style scoped>
.replay-bar {
  position: absolute; left: 50%; bottom: 44px; transform: translateX(-50%); z-index: 20;
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px; max-width: calc(100% - 24px);
  padding: 6px 10px; border-radius: 10px; background: rgba(15, 18, 26, 0.95); border: 1px solid rgba(227, 173, 66, 0.5);
  color: #e8ebf0; font-size: 12.5px;
}
.title { font-weight: 600; color: #e3ad42; margin-right: 2px; }
.when { font-variant-numeric: tabular-nums; color: #c9ced6; min-width: 190px; }
button, select, input { font: inherit; color: #e8ebf0; background: #1a2030; border: 1px solid #2c3446; border-radius: 6px; padding: 4px 8px; cursor: pointer; }
input { color-scheme: dark; }
button.go { background: rgba(227, 173, 66, 0.18); border-color: rgba(227, 173, 66, 0.6); }
button.exit { color: #9fb4ff; }
button:disabled { opacity: 0.45; cursor: default; }
</style>
