<template>
  <div ref="box" class="gpm" data-testid="game-plan-mini-chart">
    <div class="gpm-head">
      <span>{{ symbol }} · 5m · {{ plan.label }}</span>
      <span v-if="readout" class="gpm-readout">{{ readout }}</span>
    </div>
    <canvas
      ref="cv"
      class="gpm-canvas"
      role="img"
      :aria-label="`${symbol} price today with the game plan targets`"
      @pointermove="onMove"
      @pointerleave="hover = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { isCarried, levelStatus, type Board, type DayPlan } from '@/utils/chart/gamePlan';

defineOptions({ name: 'GamePlanMiniChart' });

const props = defineProps<{ plan: DayPlan; board: Board; t: number; price: number }>();

const box = ref<HTMLDivElement | null>(null);
const cv = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ x: number; y: number } | null>(null);
const symbol = computed(() => props.plan.symbol || 'ES');

const PAD_R = 58;
const PAD_T = 6;
const PAD_B = 16;
const STEP = 300_000;
const C = { up: '#2fb67c', down: '#e5534b', gold: '#e9c46a', dim: '#5d6474', text: '#8a919c', bg: '#131722', rth: 'rgba(76, 155, 232, 0.07)' };
const clock = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' });
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The day's 5-minute path with the live price folded into the last bucket. */
const path = computed<number[][]>(() => {
  const p = props.plan.path ?? [];
  const out = p.map((r) => [...r]);
  if (Number.isFinite(props.price) && props.t >= props.plan.start) {
    const b = Math.floor(props.t / STEP) * STEP;
    const last = out[out.length - 1];
    if (last && last[0] === b) {
      last[1] = Math.max(last[1], props.price);
      last[2] = Math.min(last[2], props.price);
      last[3] = props.price;
    } else if (!last || b > last[0]) out.push([b, props.price, props.price, props.price]);
  }
  return out;
});

/** Lines and hit dots on screen, for naming the one under the pointer. */
let lines: { y: number; text: string; x?: number }[] = [];
let geom: { x: (ms: number) => number; y: (p: number) => number; inv: (x: number) => number; pw: number } | null = null;

const readout = computed(() => {
  if (!hover.value || !geom) return '';
  void props.board;
  const h = hover.value;
  const onLine = lines
    .filter((l) => Math.abs(l.y - h.y) <= 5 && (l.x === undefined || Math.abs(l.x - h.x) <= 40))
    .sort((a, b) => Math.abs(a.y - h.y) - Math.abs(b.y - h.y))[0];
  if (onLine) return onLine.text;
  const ms = geom.inv(h.x);
  const pt = nearest(ms);
  return pt ? `${clock.format(new Date(pt[0]))} · ${fmt(pt[3])}` : '';
});

function nearest(ms: number): number[] | null {
  let best: number[] | null = null;
  for (const r of path.value) if (!best || Math.abs(r[0] - ms) < Math.abs(best[0] - ms)) best = r;
  return best;
}

function onMove(e: PointerEvent): void {
  const r = cv.value!.getBoundingClientRect();
  hover.value = { x: e.clientX - r.left, y: e.clientY - r.top };
}

function draw(): void {
  const canvas = cv.value;
  if (!canvas) return;
  const W = canvas.clientWidth;
  const H = canvas.clientHeight;
  if (!W || !H) return;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) {
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
  }
  const ctx = canvas.getContext('2d')!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const { plan, board, t } = props;
  const P = path.value;
  const pw = W - PAD_R;
  const ph = H - PAD_T - PAD_B;
  const span = plan.end - plan.start;
  const x = (ms: number): number => ((ms - plan.start) / span) * pw;

  // Price range: today's path, plus the nearest target each side and the latest hits.
  let hi = -Infinity;
  let lo = Infinity;
  for (const r of P) { hi = Math.max(hi, r[1]); lo = Math.min(lo, r[2]); }
  if (!Number.isFinite(hi)) { hi = props.price + 5; lo = props.price - 5; }
  const rng = Math.max(hi - lo, 10);
  const hits = board.done.slice(0, 3).map((r) => r.level);
  const near = [board.above[board.above.length - 1]?.level, board.below[0]?.level].filter(Boolean);
  for (const l of [...near, ...hits]) if (l && Math.abs(l.price - props.price) < rng * 1.5) { hi = Math.max(hi, l.price); lo = Math.min(lo, l.price); }
  const pad = (hi - lo) * 0.08;
  hi += pad;
  lo -= pad;
  const y = (p: number): number => PAD_T + ((hi - p) / (hi - lo)) * ph;
  geom = { x, y, inv: (px) => plan.start + (px / pw) * span, pw };

  // RTH band and time marks.
  const r0 = x(plan.ctx.rth0);
  const r1 = x(plan.ctx.rth1);
  ctx.fillStyle = C.rth;
  ctx.fillRect(r0, PAD_T, r1 - r0, ph);
  ctx.font = '10px -apple-system, "Segoe UI", Roboto, sans-serif';
  ctx.fillStyle = C.dim;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  const marks: [number, string][] = [[plan.start + 9 * 3_600_000, '12 AM'], [plan.ctx.rth0, '6:30'], [plan.ctx.rth1, '1 PM']];
  for (const [ms, lab] of marks) { const mx = x(ms); if (mx > 14 && mx < pw - 10) ctx.fillText(lab, mx, H - 4); }

  // Open targets: dashed when carried, label over the line, price tag on the right.
  const tags: { y: number; text: string; color: string }[] = [];
  lines = [];
  const crisp = (v: number): number => Math.round(v) + 0.5;
  for (const row of [...board.above, ...board.below]) {
    const l = row.level;
    const ly = y(l.price);
    if (ly < PAD_T - 1 || ly > PAD_T + ph + 1) continue;
    const carried = isCarried(l, t);
    const from = carried && !l.fromDay ? Math.max(l.frm, l.origUntil) : l.frm;
    ctx.strokeStyle = l.color;
    ctx.globalAlpha = carried ? 0.75 : 1;
    ctx.setLineDash(carried || l.kind === 'hour_open' ? [4, 3] : []);
    ctx.beginPath();
    ctx.moveTo(Math.max(0, x(from)), crisp(ly));
    ctx.lineTo(pw, crisp(ly));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    tags.push({ y: ly, text: fmt(l.price), color: l.color });
    lines.push({ y: ly, text: `${carried ? '↻ ' : ''}${l.label}${row.odds.value !== null ? ` · ${row.odds.value}%` : ''} · ${fmt(l.price)}` });
  }

  // Latest hits: a short stub ending in a check dot.
  for (const l of hits) {
    if (l.hitAt === null || levelStatus(l, t) !== 'done') continue;
    const hx = x(l.hitAt);
    const hy = y(l.price);
    if (hy < PAD_T || hy > PAD_T + ph) continue;
    ctx.strokeStyle = l.color;
    ctx.beginPath();
    ctx.moveTo(Math.max(0, hx - 34), crisp(hy));
    ctx.lineTo(hx, crisp(hy));
    ctx.stroke();
    ctx.fillStyle = C.up;
    ctx.beginPath();
    ctx.arc(hx, hy, 3.5, 0, Math.PI * 2);
    ctx.fill();
    lines.push({ y: hy, text: `✓ ${l.label} hit ${clock.format(new Date(l.hitAt))}`, x: hx });
  }

  // The price line.
  const move = plan.ctx.dayOpen !== undefined ? props.price - plan.ctx.dayOpen : 0;
  ctx.strokeStyle = move < 0 ? C.down : C.up;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  P.forEach((r, i) => { const px = x(r[0] + STEP / 2); const py = y(r[3]); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); });
  ctx.stroke();
  ctx.lineWidth = 1;

  // Last price.
  const py = y(props.price);
  ctx.strokeStyle = C.gold;
  ctx.setLineDash([1, 3]);
  ctx.beginPath();
  ctx.moveTo(0, crisp(py));
  ctx.lineTo(pw, crisp(py));
  ctx.stroke();
  ctx.setLineDash([]);

  // Price tags on the right, spread so they never overlap; the live price wins its spot.
  const all = [...tags, { y: py, text: fmt(props.price), color: C.gold }].sort((a, b) => a.y - b.y);
  for (let i = 1; i < all.length; i++) if (all[i].y - all[i - 1].y < 15) all[i].y = all[i - 1].y + 15;
  ctx.font = '10px ui-monospace, Menlo, monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const tg of all) {
    const ty = Math.min(H - PAD_B - 2, Math.max(PAD_T + 6, tg.y));
    ctx.fillStyle = tg.color;
    ctx.fillRect(pw + 3, ty - 7, PAD_R - 4, 14);
    ctx.fillStyle = '#0d1017';
    ctx.fillText(tg.text, pw + 3 + (PAD_R - 4) / 2, ty + 0.5);
  }

  // Hover crosshair.
  if (hover.value && hover.value.x < pw) {
    const pt = nearest(geom.inv(hover.value.x));
    if (pt) {
      const hx = x(pt[0] + STEP / 2);
      ctx.strokeStyle = 'rgba(215, 219, 227, 0.35)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(crisp(hx), PAD_T);
      ctx.lineTo(crisp(hx), PAD_T + ph);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#d7dbe3';
      ctx.beginPath();
      ctx.arc(hx, y(pt[3]), 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

let ro: ResizeObserver | null = null;
onMounted(() => {
  ro = new ResizeObserver(() => draw());
  if (box.value) ro.observe(box.value);
  void nextTick(draw);
});
onBeforeUnmount(() => ro?.disconnect());
watch(() => [props.plan, props.board, props.t, props.price, hover.value], () => draw());
</script>

<style scoped>
.gpm { flex: 1 1 auto; min-height: 190px; display: flex; flex-direction: column; gap: 4px; border-top: 1px solid rgba(255, 255, 255, 0.06); padding-top: 10px; }
.gpm-head { display: flex; justify-content: space-between; gap: 6px; color: #5d6474; font-size: 11px; min-height: 15px; }
.gpm-head > span:first-child { white-space: nowrap; }
.gpm-readout { color: #d7dbe3; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; font-family: ui-monospace, Menlo, monospace; font-variant-numeric: tabular-nums; }
.gpm-canvas { flex: 1 1 auto; width: 100%; min-height: 170px; display: block; cursor: crosshair; touch-action: none; }
</style>
