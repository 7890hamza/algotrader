<template>
  <div ref="box" class="gpm" data-testid="game-plan-mini-chart">
    <div class="gpm-head">
      <span class="gpm-title">{{ symbol }} · 5m · {{ plan.label }}</span>
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

import { isCarried, levelStatus, type Board, type DayPlan, type PlanLevel } from '@/utils/chart/gamePlan';

defineOptions({ name: 'GamePlanMiniChart' });

const props = defineProps<{ plan: DayPlan; board: Board; t: number; price: number }>();

const box = ref<HTMLDivElement | null>(null);
const cv = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ x: number; y: number } | null>(null);
const symbol = computed(() => props.plan.symbol || 'ES');

const HOUR = 3_600_000;
const STEP = 300_000;
const SMOOTH = 15 * 60_000; // the line is drawn from 15-minute closes, like the mockup
const PAD_R = 62;
const PAD_T = 16;
const PAD_B = 20;
const FONT = '11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const MONO = '11px ui-monospace, Menlo, Consolas, monospace';
const C = { up: '#2fb67c', down: '#e5534b', gold: '#e9c46a', axis: '#8a919c', rth: 'rgba(76, 155, 232, 0.07)', panel: '#131722', tagText: '#0d1017' };
const clock = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' });
const fmt = (v: number): string => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const short = (label: string): string => label.replace(/ extension$/, '').replace(/^Yesterday's /, 'Yday ').replace(/ \((pETH|pRTH)\)$/, '');

/** The day's 5-minute path with the live price folded into the last bucket. */
const path = computed<number[][]>(() => {
  const out = (props.plan.path ?? []).map((r) => [...r]);
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
let hoverables: { y: number; text: string; x0: number; x1: number }[] = [];
let geom: { inv: (x: number) => number; pw: number } | null = null;

const readout = computed(() => {
  if (!hover.value || !geom) return '';
  void props.t;
  const h = hover.value;
  const hit = hoverables
    .filter((l) => Math.abs(l.y - h.y) <= 5 && h.x >= l.x0 - 4 && h.x <= l.x1 + 4)
    .sort((a, b) => Math.abs(a.y - h.y) - Math.abs(b.y - h.y))[0];
  if (hit) return hit.text;
  const pt = nearest(geom.inv(h.x));
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

/** Pacific-time ticks: 3 AM, 6:30, 10 AM and 1 PM of the trading day (6 PM / 12 AM early on). */
function ticks(plan: DayPlan): [number, string][] {
  const d0 = plan.start + 9 * HOUR; // midnight PT
  return [[plan.start + 3 * HOUR, '6 PM'], [d0, '12 AM'], [d0 + 3 * HOUR, '3 AM'], [plan.ctx.rth0, '6:30'], [d0 + 10 * HOUR, '10 AM'], [plan.ctx.rth1, '1 PM']];
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
  const { plan, board, t, price } = props;
  const pw = W - PAD_R;
  const ph = H - PAD_T - PAD_B;

  // Time window: the last ~13 hours up to a little past the RTH close (the whole day early on).
  const x0t = Math.max(plan.start, Math.min(t, plan.ctx.rth1) - 13 * HOUR);
  const x1t = Math.min(plan.end, Math.max(t, plan.ctx.rth1) + 40 * 60_000);
  const x = (ms: number): number => ((ms - x0t) / (x1t - x0t)) * pw;
  geom = { inv: (px) => x0t + (px / pw) * (x1t - x0t), pw };

  // 15-minute closes inside the window.
  const pts: number[][] = [];
  for (const r of path.value) {
    if (r[0] < x0t) continue;
    const b = Math.floor(r[0] / SMOOTH) * SMOOTH;
    const last = pts[pts.length - 1];
    if (last && last[0] === b) { last[1] = Math.max(last[1], r[1]); last[2] = Math.min(last[2], r[2]); last[3] = r[3]; } else pts.push([b, r[1], r[2], r[3]]);
  }

  // Which levels: the nearest two open targets above, one or two below, and the last two hits.
  const open = [...board.above.slice(-2), ...board.below.slice(0, 2)].map((r) => r);
  const hits = board.done.filter((r) => r.level.hitAt !== null && r.level.hitAt >= x0t).slice(0, 2).map((r) => r.level);

  let hi = -Infinity;
  let lo = Infinity;
  for (const r of pts) { hi = Math.max(hi, r[1]); lo = Math.min(lo, r[2]); }
  if (!Number.isFinite(hi)) { hi = price + 5; lo = price - 5; }
  for (const l of [...open.map((r) => r.level), ...hits]) { hi = Math.max(hi, l.price); lo = Math.min(lo, l.price); }
  hi = Math.max(hi, price);
  lo = Math.min(lo, price);
  const pad = Math.max(2, (hi - lo) * 0.06);
  hi += pad;
  lo -= pad;
  const y = (p: number): number => PAD_T + ((hi - p) / (hi - lo)) * ph;
  const crisp = (v: number): number => Math.round(v) + 0.5;

  // RTH band.
  const r0 = Math.max(0, x(plan.ctx.rth0));
  const r1 = Math.min(pw, x(plan.ctx.rth1));
  if (r1 > r0) { ctx.fillStyle = C.rth; ctx.fillRect(r0, PAD_T - 6, r1 - r0, ph + 6); }

  // Time axis.
  ctx.font = FONT;
  ctx.fillStyle = C.axis;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  let lastX = -1e9;
  for (const [ms, lab] of ticks(plan)) {
    const tx = x(ms);
    if (tx < 14 || tx > pw - 12 || tx - lastX < 34) continue;
    ctx.fillText(lab, tx, H - 5);
    lastX = tx;
  }

  hoverables = [];
  const tags: { y: number; text: string; color: string }[] = [];
  const labels: { x: number; y: number; text: string; color: string; align: CanvasTextAlign }[] = [];

  // Open targets: dashed when carried, the name right-aligned just above the line.
  const drawOpen = (l: PlanLevel, oddsText: string | null): void => {
    const ly = y(l.price);
    const carried = isCarried(l, t);
    const from = Math.max(0, x(l.frm));
    const xs = Math.min(from, pw - 36);
    ctx.strokeStyle = l.color;
    ctx.lineWidth = 1;
    ctx.globalAlpha = carried ? 0.8 : 1;
    ctx.setLineDash(carried || l.kind === 'hour_open' ? [5, 4] : []);
    ctx.beginPath();
    ctx.moveTo(xs, crisp(ly));
    ctx.lineTo(pw, crisp(ly));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    const name = `${carried ? '↻ ' : ''}${short(l.label)}${oddsText ? ` · ${oddsText}` : ''}`;
    labels.push({ x: pw - 4, y: ly, text: name, color: l.color, align: 'right' });
    tags.push({ y: ly, text: fmt(l.price), color: l.color });
    hoverables.push({ y: ly, x0: xs, x1: pw, text: `${carried ? '↻ ' : ''}${l.label}${oddsText ? ` · ${oddsText}` : ''} · ${fmt(l.price)}` });
  };
  for (const r of open) drawOpen(r.level, r.odds.value !== null ? `${Math.round(r.odds.value)}%` : null);

  // Latest hits: a short line ending in a green dot, the name over the line.
  for (const l of hits) {
    if (levelStatus(l, t) !== 'done' || l.hitAt === null) continue;
    const hx = x(l.hitAt);
    const hy = y(l.price);
    const sx = Math.max(0, hx - 52);
    ctx.strokeStyle = l.color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(sx, crisp(hy));
    ctx.lineTo(hx, crisp(hy));
    ctx.stroke();
    ctx.fillStyle = C.up;
    ctx.beginPath();
    ctx.arc(hx, hy, 3.5, 0, Math.PI * 2);
    ctx.fill();
    labels.push({ x: (sx + hx) / 2, y: hy, text: short(l.label), color: l.color, align: 'center' });
    hoverables.push({ y: hy, x0: sx, x1: hx, text: `✓ ${l.label} hit at ${clock.format(new Date(l.hitAt))} · ${fmt(l.price)}` });
  }

  // The price line.
  const move = plan.ctx.dayOpen !== undefined ? price - plan.ctx.dayOpen : 0;
  ctx.strokeStyle = move < 0 ? C.down : C.up;
  ctx.lineWidth = 1.6;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  pts.forEach((r, i) => {
    const px = i === pts.length - 1 ? x(Math.min(t, r[0] + SMOOTH)) : x(r[0] + SMOOTH / 2);
    const py = y(i === pts.length - 1 ? price : r[3]);
    if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
  });
  ctx.stroke();
  ctx.lineWidth = 1;

  // Last price: dotted gold line across.
  const py = y(price);
  ctx.strokeStyle = 'rgba(215, 219, 227, 0.55)';
  ctx.setLineDash([1, 3]);
  ctx.beginPath();
  ctx.moveTo(0, crisp(py));
  ctx.lineTo(pw, crisp(py));
  ctx.stroke();
  ctx.setLineDash([]);

  // Names over the lines, dropping any that would sit on top of another.
  ctx.font = FONT;
  ctx.textBaseline = 'bottom';
  const placed: { x0: number; x1: number; y: number }[] = [];
  for (const lb of labels.sort((a, b) => a.y - b.y)) {
    const w = ctx.measureText(lb.text).width;
    const lx0 = lb.align === 'right' ? lb.x - w : lb.align === 'center' ? lb.x - w / 2 : lb.x;
    const ty = lb.y - 3;
    if (placed.some((p) => Math.abs(p.y - ty) < 12 && lx0 < p.x1 && lx0 + w > p.x0)) continue;
    placed.push({ x0: lx0, x1: lx0 + w, y: ty });
    ctx.fillStyle = lb.color;
    ctx.textAlign = lb.align;
    ctx.fillText(lb.text, lb.x, ty);
  }

  // Price tags on the right; the live price is the gold one.
  const all = [...tags, { y: py, text: fmt(price), color: C.gold }].sort((a, b) => a.y - b.y);
  for (let i = 1; i < all.length; i++) if (all[i].y - all[i - 1].y < 18) all[i].y = all[i - 1].y + 18;
  ctx.font = MONO;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const tg of all) {
    const ty = Math.min(H - PAD_B - 8, Math.max(9, tg.y));
    ctx.fillStyle = tg.color;
    ctx.fillRect(pw + 4, ty - 8, PAD_R - 6, 16);
    ctx.fillStyle = C.tagText;
    ctx.fillText(tg.text, pw + 4 + (PAD_R - 6) / 2, ty + 0.5);
  }

  // Hover crosshair.
  if (hover.value && hover.value.x < pw) {
    const pt = nearest(geom.inv(hover.value.x));
    if (pt) {
      const hx = x(pt[0] + STEP / 2);
      ctx.strokeStyle = 'rgba(215, 219, 227, 0.3)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(crisp(hx), PAD_T - 6);
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
.gpm {
  flex: 1 1 auto;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #131722;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 8px;
  padding: 10px 6px 4px 10px;
}
.gpm-head { display: flex; justify-content: space-between; gap: 6px; color: #8a919c; font-size: 11px; min-height: 15px; }
.gpm-title { white-space: nowrap; }
.gpm-readout { color: #d7dbe3; font-family: ui-monospace, Menlo, monospace; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.gpm-canvas { flex: 1 1 auto; width: 100%; min-height: 260px; display: block; cursor: crosshair; touch-action: none; }
</style>
