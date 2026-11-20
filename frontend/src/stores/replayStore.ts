import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import { IS_REPLAY, REPLAY_START_MS } from '@/utils/replay';

/** Replay playback: the cursor (last bar shown), play / pause and speed. */
export const useReplayStore = defineStore('replay', () => {
  const active = IS_REPLAY;
  const cursorMs = ref<number>(REPLAY_START_MS ?? Number.POSITIVE_INFINITY);
  const playing = ref(false);
  const msPerBar = ref(250);
  const pickerOpen = ref(false);
  /** Bar times (ms) the chart loaded, oldest first; set by the chart. */
  const barTimes = ref<number[]>([]);

  const index = computed(() => {
    const times = barTimes.value;
    let lo = 0; let hi = times.length - 1; let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (times[mid] <= cursorMs.value) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return found;
  });
  const atEnd = computed(() => index.value >= barTimes.value.length - 1);

  function step(bars = 1): void {
    const times = barTimes.value;
    if (!times.length) return;
    const next = Math.max(0, Math.min(times.length - 1, index.value + bars));
    cursorMs.value = times[next];
    if (next >= times.length - 1) playing.value = false;
  }
  function jump(ms: number): void {
    const times = barTimes.value;
    const target = cursorMs.value + ms;
    const next = times.findIndex((t) => t > target);
    cursorMs.value = next < 0 ? times[times.length - 1] ?? cursorMs.value : times[Math.max(0, next - 1)];
  }

  let timer: ReturnType<typeof setInterval> | null = null;
  function setPlaying(on: boolean): void {
    playing.value = on && !atEnd.value;
    if (timer) { clearInterval(timer); timer = null; }
    if (playing.value) timer = setInterval(() => { if (playing.value) step(1); else setPlaying(false); }, msPerBar.value);
  }
  function setSpeed(ms: number): void {
    msPerBar.value = ms;
    if (playing.value) setPlaying(true);
  }

  return { active, cursorMs, playing, msPerBar, pickerOpen, barTimes, index, atEnd, step, jump, setPlaying, setSpeed };
});
