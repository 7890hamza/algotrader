<template>
  <div v-if="replay.active || replay.pickerOpen" class="replay-bar" data-testid="replay-bar">
    <template v-if="!replay.active">
      <span class="title">Replay from</span>
      <input id="replay-date" v-model="pickDay" type="date" :max="today" aria-label="Day to replay">
      <button type="button" class="go" :disabled="!pickDay" @click="start">Start replay</button>
      <select id="replay-stacks" v-model="stackPick" aria-label="Jump to a stats stack" class="stacks" @change="goStack">
        <option value="">Stacks…</option>
        <optgroup v-for="m in stackMonths" :key="m.name" :label="m.name">
          <option v-for="r in m.rows" :key="r.value" :value="r.value">{{ r.text }}</option>
        </optgroup>
      </select>

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
      <select id="replay-stacks" v-model="stackPick" aria-label="Jump to a stats stack" class="stacks" @change="goStack">
        <option value="">Stacks…</option>
        <optgroup v-for="m in stackMonths" :key="m.name" :label="m.name">
          <option v-for="r in m.rows" :key="r.value" :value="r.value">{{ r.text }}</option>
        </optgroup>
      </select>
      <input id="replay-jump" v-model="pickDay" type="date" :max="today" aria-label="Replay another day" @change="start">
      <button type="button" class="exit" @click="exit">Back to live</button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

import stackMoments from '@/data/stackMoments.json';
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

// Moments in 2026 ES where 6+ Game Plan stats were hit one after another in one direction.
const stackPick = ref('');
const pt = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-US', { timeZone: DEFAULT_CHART_TIME_ZONE, ...opts });
const stackMonths = computed(() => {
  const months = new Map<string, { name: string; rows: { value: string; text: string }[] }>();
  for (const [from, , dir, n] of (stackMoments as { rows: number[][] }).rows) {
    const d = new Date(from);
    const name = pt({ month: 'long', year: 'numeric' }).format(d);
    if (!months.has(name)) months.set(name, { name, rows: [] });
    months.get(name)!.rows.push({ value: String(from), text: `${pt({ weekday: 'short', month: 'short', day: 'numeric' }).format(d)} · ${pt({ hour: 'numeric', minute: '2-digit' }).format(d)} · ${n} stats ${dir > 0 ? '▲' : '▼'}` });
  }
  return [...months.values()].reverse();
});
function goStack(): void {
  const ms = Number(stackPick.value);
  if (ms) location.href = replayUrl(ms - 45 * 60_000); // start a little before, then press Play
}

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
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px; width: max-content; max-width: calc(100% - 24px);
  padding: 6px 10px; border-radius: 10px; background: rgba(15, 18, 26, 0.95); border: 1px solid rgba(227, 173, 66, 0.5);
  color: #e8ebf0; font-size: 12.5px;
}
.title { font-weight: 600; color: #e3ad42; margin-right: 2px; }
.when { font-variant-numeric: tabular-nums; color: #c9ced6; white-space: nowrap; }
button, select, input { font: inherit; color: #e8ebf0; background: #1a2030; border: 1px solid #2c3446; border-radius: 6px; padding: 4px 8px; cursor: pointer; }
input { color-scheme: dark; }
input[type=date] { width: 128px; }
button.go { background: rgba(227, 173, 66, 0.18); border-color: rgba(227, 173, 66, 0.6); }
button.exit { color: #9fb4ff; }
select.stacks { width: 150px; border-color: rgba(47, 182, 124, 0.55); }
button:disabled { opacity: 0.45; cursor: default; }
</style>
