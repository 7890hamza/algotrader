import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, ISeriesPrimitiveAxisView, Logical, SeriesAttachedParameter, Time } from 'lightweight-charts';

import { cmeClock } from '@/utils/dailyCandle';
import { getStoredState, setStoredState } from '@/utils/localStorage';

import type { ManagedSeriesApi } from './ChartManager';
import {
  BOOKMARK_COLOR, COLORS, distToSegment, logicalToTime, magnet, newId, pointValue, rayEnd, timeToLogical, touches, touchInfo, TWO_POINT,
  type DPoint, type DrawKind, type Drawing,
} from './drawings';

const FONT = '600 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const TEXT_FONT = '600 13px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const HIT = 6;
const HANDLE = 5;

export interface DrawBar { t: number; o: number; h: number; l: number; c: number }
export type DrawPart = 'a' | 'b' | 'body';
interface Shape {
  d: Drawing;
  handles: { part: 'a' | 'b'; x: number; y: number }[];
  segs: [number, number, number, number][];
  box: { x0: number; y0: number; x1: number; y1: number } | null; // rectangle / text: click inside selects
}

const fmt = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

class DrawingPrimitive implements ISeriesPrimitive<Time> {
  private param: SeriesAttachedParameter<Time> | null = null;
  drawings: Drawing[] = [];
  preview: Drawing | null = null;
  selectedId: string | null = null;
  hidden = false;
  times: number[] = [];
  bars: DrawBar[] = [];
  barMs = 60_000;
  shapes: Shape[] = [];
  /** bookmark being hovered or dragged: its info card shows */
  cardId: string | null = null;
  symbol: string | null = null;
  levelsNear: (price: number) => string[] = () => [];

  attached(p: SeriesAttachedParameter<Time>): void { this.param = p; }
  detached(): void { this.param = null; }
  update(): void { this.param?.requestUpdate(); }
  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = { draw: (t) => this.draw(t) };
    return [{ zOrder: () => 'top', renderer: () => renderer }];
  }

  /** Bookmarks get their own yellow price tag on the price axis. */
  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    if (this.hidden) return [];
    return this.drawings.filter((d) => d.kind === 'bookmark').map((d) => ({
      coordinate: () => this.y(d.a.p) ?? -100,
      text: () => fmt(d.a.p),
      textColor: () => '#131722',
      backColor: () => d.color,
    }));
  }

  x(t: number): number | null {
    return this.param?.chart.timeScale().logicalToCoordinate(timeToLogical(this.times, this.barMs, t) as Logical) ?? null;
  }
  y(p: number): number | null { return this.param?.series.priceToCoordinate(p) ?? null; }

  private shape(d: Drawing, W: number, H: number): Shape | null {
    const ax = this.x(d.a.t); const ay = this.y(d.a.p);
    if (ax === null || ay === null) return null;
    const s: Shape = { d, handles: [{ part: 'a', x: ax, y: ay }], segs: [], box: null };
    if (d.kind === 'hline') { s.segs.push([0, ay, W, ay]); return s; }
    if (d.kind === 'bookmark') {
      // the line, and the magnifier near the right edge as its handle
      s.segs.push([0, ay, W, ay]);
      s.handles = [{ part: 'a', x: W - 24, y: ay }];
      s.box = { x0: W - 36, y0: ay - 12, x1: W - 8, y1: ay + 12 };
      return s;
    }
    if (d.kind === 'hray') { s.segs.push([ax, ay, W, ay]); return s; }
    if (d.kind === 'vline') { s.segs.push([ax, 0, ax, H]); s.handles[0].y = Math.max(20, Math.min(H - 20, ay)); return s; }
    if (d.kind === 'text') {
      const w = Math.max(30, (d.text ?? '').length * 7.5 + 14);
      s.box = { x0: ax, y0: ay - 22, x1: ax + w, y1: ay };
      return s;
    }
    if (!d.b) return null;
    const bx = this.x(d.b.t); const by = this.y(d.b.p);
    if (bx === null || by === null) return null;
    s.handles.push({ part: 'b', x: bx, y: by });
    if (d.kind === 'trend') s.segs.push([ax, ay, bx, by]);
    else if (d.kind === 'ray') { const [ex, ey] = rayEnd(ax, ay, bx, by, W); s.segs.push([ax, ay, ex, ey]); }
    else if (d.kind === 'rect') {
      const x0 = Math.min(ax, bx); const x1 = Math.max(ax, bx); const y0 = Math.min(ay, by); const y1 = Math.max(ay, by);
      s.box = { x0, y0, x1, y1 };
      s.segs.push([x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]);
    }
    return s;
  }

  hit(px: number, py: number): { id: string; part: DrawPart } | null {
    // the selected drawing's handles first, then anything else, newest on top
    const order = [...this.shapes].sort((p, q) => Number(q.d.id === this.selectedId) - Number(p.d.id === this.selectedId));
    for (const s of order) {
      if (s.d.id !== this.selectedId) continue;
      for (const h of s.handles) if (Math.hypot(px - h.x, py - h.y) <= HANDLE + 4) return { id: s.d.id, part: h.part };
    }
    for (const s of [...order].reverse()) {
      if (s.segs.some(([a, b, c, d]) => distToSegment(px, py, a, b, c, d) <= HIT)) return { id: s.d.id, part: 'body' };
      if (s.box && px >= s.box.x0 && px <= s.box.x1 && py >= s.box.y0 && py <= s.box.y1) return { id: s.d.id, part: 'body' };
    }
    return null;
  }

  private draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width; const H = mediaSize.height;
      this.shapes = [];
      const list = this.hidden ? [] : [...this.drawings];
      if (this.preview) list.push(this.preview);
      for (const d of list) {
        const s = this.shape(d, W, H);
        if (!s) continue;
        if (d !== this.preview) this.shapes.push(s);
        const sel = d.id === this.selectedId || d === this.preview;
        ctx.strokeStyle = d.color; ctx.lineWidth = sel ? 2.5 : 2; ctx.setLineDash(d.dashed ? [6, 5] : []);
        if (d.kind === 'rect' && s.box) {
          ctx.fillStyle = `${d.color}22`; ctx.fillRect(s.box.x0, s.box.y0, s.box.x1 - s.box.x0, s.box.y1 - s.box.y0);
        }
        for (const [a, b, c, e] of s.segs) { ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, e); ctx.stroke(); }
        ctx.setLineDash([]);
        if (d.kind === 'text' && s.box) {
          ctx.fillStyle = 'rgba(19, 23, 34, 0.85)'; ctx.fillRect(s.box.x0, s.box.y0, s.box.x1 - s.box.x0, s.box.y1 - s.box.y0);
          ctx.strokeStyle = sel ? d.color : `${d.color}88`; ctx.lineWidth = 1; ctx.strokeRect(s.box.x0 + 0.5, s.box.y0 + 0.5, s.box.x1 - s.box.x0 - 1, s.box.y1 - s.box.y0 - 1);
          ctx.font = TEXT_FONT; ctx.fillStyle = d.color; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
          ctx.fillText(d.text ?? '', s.box.x0 + 7, (s.box.y0 + s.box.y1) / 2 + 0.5);
        }
        if (d.kind === 'bookmark') { this.drawMagnifier(ctx, W - 24, s.segs[0][1], d.color); if (this.cardId === d.id) this.drawCard(ctx, W, s.segs[0][1], d); continue; }
        // levels: price and how many times price came back to it
        if (d.kind === 'hline' || d.kind === 'hray') {
          const n = touches(this.bars, d.a.p, d.a.t);
          const label = `${fmt(d.a.p)}${n ? ` · touched ${n}×` : ''}`;
          ctx.font = FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillStyle = d.color;
          ctx.fillText(label, W - 6, s.segs[0][1] - 3);
        }
        if (d.kind === 'rect' && s.box && sel && d.b) {
          const pts = Math.abs(d.a.p - d.b.p);
          ctx.font = FONT; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'; ctx.fillStyle = d.color;
          ctx.fillText(`${fmt(pts)} pts`, s.box.x0 + 4, s.box.y0 - 3);
        }
        if (sel) {
          for (const h of s.handles) {
            ctx.fillStyle = '#131722'; ctx.strokeStyle = d.color; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(h.x, h.y, HANDLE, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          }
        }
      }
    });
  }

  private drawMagnifier(ctx: CanvasRenderingContext2D, x: number, y: number, color: string): void {
    ctx.fillStyle = '#131722'; ctx.strokeStyle = color; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x + 5, y + 5); ctx.lineTo(x + 11, y + 11); ctx.stroke();
  }

  /** What the bookmark is looking at: distance from price, $ per contract, levels there, touches today. */
  private drawCard(ctx: CanvasRenderingContext2D, W: number, y: number, d: Drawing): void {
    const p = d.a.p; const last = this.bars[this.bars.length - 1];
    const lines: CardLine[] = [{ text: fmt(p), color: d.color, bold: true }];
    if (last) {
      const dist = p - last.c;
      const usd = pointValue(this.symbol).map((v) => `$${Math.round(Math.abs(dist) * v.usd).toLocaleString('en-US')} on 1 ${v.label}`).join(' / ');
      lines.push({ text: `${fmt(Math.abs(dist))} pts ${dist >= 0 ? 'above' : 'below'} price${usd ? ` · ${usd}` : ''}`, color: '#e6e9ef' });
      const dayStart = last.t - cmeClock(last.t).dm * 60_000;
      const ti = touchInfo(this.bars, p, dayStart);
      const when = ti.lastT !== null ? new Date(ti.lastT).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles' }) : '';
      lines.push({
        text: ti.count ? `Touched ${ti.count}× today · last ${when}${ti.awayPts ? `, moved ${fmt(ti.awayPts)} pts away since` : ''}` : 'Not touched today',
        color: '#b8c0cc',
      });
    }
    const near = this.levelsNear(p);
    lines.push({ text: near.length ? `Levels here (±1.5 pts): ${near.join(' · ')}` : 'No other levels within 1.5 pts', color: '#b8c0cc' });
    ctx.font = FONT;
    const w = Math.max(...lines.map((l) => ctx.measureText(l.text).width)) + 20;
    const h = lines.length * 17 + 10;
    const x0 = Math.max(4, W - 44 - w); const y0 = y - h - 12 > 4 ? y - h - 12 : y + 14;
    ctx.fillStyle = 'rgba(28, 33, 48, 0.96)'; ctx.fillRect(x0, y0, w, h);
    ctx.strokeStyle = d.color; ctx.lineWidth = 1; ctx.strokeRect(x0 + 0.5, y0 + 0.5, w - 1, h - 1);
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    lines.forEach((l, i) => {
      ctx.font = l.bold ? '700 13px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif' : FONT;
      ctx.fillStyle = l.color; ctx.fillText(l.text, x0 + 10, y0 + 14 + i * 17);
    });
  }
}

// ---- bookmark pieces -------------------------------------------------------------------------
interface CardLine { text: string; color: string; bold?: boolean }

export interface DrawingHost {
  getSeries(): ManagedSeriesApi | null;
  coordinateToPrice(y: number): number | null;
  coordinateToLogical(x: number): number | null;
  bars(): DrawBar[];
  barMs(): number;
  setDragScroll(enabled: boolean): void;
  /** another tool (Long / Short / Retrace / measure) owns the mouse right now */
  busy(): boolean;
  onChange(state: { tool: DrawKind | null; selected: Drawing | null; count: number; hidden: boolean; magnet: boolean }): void;
  /** names of other levels within 1.5 points of a price (for the bookmark card) */
  levelsNear?(price: number): string[];
}

interface Stored { drawings: Drawing[]; color: string }
const key = (symbol: string) => `algotrader_drawings:${symbol}`;
const PREFS = 'algotrader_drawings_prefs';

/**
 * TradingView-style drawings on one chart. Pick a tool, click once (lines, text) or twice (trend,
 * ray, rectangle). Click a drawing to select it, drag its dots to reshape, drag the line to move it,
 * Delete to remove it, Esc to cancel. Kept per symbol in this browser.
 */
export class DrawingController {
  private readonly prim = new DrawingPrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private pane: HTMLElement | null = null;
  private symbol: string | null = null;
  private store: Stored = { drawings: [], color: COLORS[0] };
  private tool: DrawKind | null = null;
  private first: DPoint | null = null;
  private drag: { id: string; part: DrawPart; start: DPoint; a: DPoint; b?: DPoint } | null = null;
  private magnetOn = true;

  constructor(private readonly host: DrawingHost) {
    const prefs = getStoredState<{ hidden?: boolean; magnet?: boolean }>(PREFS);
    this.prim.hidden = prefs?.hidden ?? false;
    this.magnetOn = prefs?.magnet ?? true;
    this.prim.levelsNear = (price) => this.host.levelsNear?.(price) ?? [];
    window.addEventListener('keydown', this.onKey);
  }

  setSymbol(symbol: string | null): void {
    if (symbol === this.symbol) return;
    this.symbol = symbol;
    this.prim.symbol = symbol;
    const saved = symbol ? getStoredState<Stored>(key(symbol)) : null;
    this.store = saved && Array.isArray(saved.drawings) ? saved : { drawings: [], color: this.store.color };
    this.prim.selectedId = null;
    this.render();
  }

  setPane(pane: HTMLElement | null): void {
    if (this.pane === pane) return;
    this.pane?.removeEventListener('pointerdown', this.onDown, true);
    this.pane?.removeEventListener('pointermove', this.onHover);
    this.pane?.removeEventListener('dblclick', this.onDouble);
    this.pane = pane;
    pane?.addEventListener('pointerdown', this.onDown, true);
    pane?.addEventListener('pointermove', this.onHover);
    pane?.addEventListener('dblclick', this.onDouble);
  }

  syncSeries(): void {
    const series = this.host.getSeries();
    if (series === this.attachedTo) { this.render(); return; }
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* gone */ }
    this.attachedTo = series;
    series?.attachPrimitive?.(this.prim);
    this.render();
  }

  /** Pick a tool (null = the normal cursor). */
  setTool(kind: DrawKind | null): void {
    this.tool = kind;
    this.first = null;
    this.prim.preview = null;
    this.host.setDragScroll(kind === null);
    if (this.pane) this.pane.style.cursor = kind ? 'crosshair' : '';
    this.render();
  }

  style(patch: { color?: string; dashed?: boolean; text?: string }): void {
    const d = this.selected();
    if (patch.color) this.store.color = patch.color;
    if (!d) { this.save(); return; }
    Object.assign(d, patch);
    this.save();
  }

  removeSelected(): void {
    const id = this.prim.selectedId;
    if (!id) return;
    this.store.drawings = this.store.drawings.filter((d) => d.id !== id);
    this.prim.selectedId = null;
    this.save();
  }

  removeAll(): void { this.store.drawings = []; this.prim.selectedId = null; this.save(); }
  toggleHidden(): void { this.prim.hidden = !this.prim.hidden; this.prim.selectedId = null; this.savePrefs(); this.render(); }
  toggleMagnet(): void { this.magnetOn = !this.magnetOn; this.savePrefs(); this.render(); }

  /** New candles: redraw (touch counts follow price). */
  refresh(): void { this.render(); }

  destroy(): void {
    window.removeEventListener('keydown', this.onKey);
    this.setPane(null);
    this.endDrag();
    try { this.attachedTo?.detachPrimitive(this.prim); } catch { /* gone */ }
    this.attachedTo = null;
  }

  private selected(): Drawing | null { return this.store.drawings.find((d) => d.id === this.prim.selectedId) ?? null; }
  private savePrefs(): void { setStoredState(PREFS, { hidden: this.prim.hidden, magnet: this.magnetOn }); }
  private save(): void { if (this.symbol) setStoredState(key(this.symbol), this.store); this.render(); }

  private render(): void {
    const bars = this.host.bars();
    this.prim.bars = bars;
    this.prim.times = bars.map((b) => b.t);
    this.prim.barMs = this.host.barMs();
    this.prim.drawings = this.store.drawings;
    this.prim.update();
    this.host.onChange({ tool: this.tool, selected: this.selected(), count: this.store.drawings.length, hidden: this.prim.hidden, magnet: this.magnetOn });
  }

  private local(e: MouseEvent): { x: number; y: number } | null {
    if (!this.pane) return null;
    const r = this.pane.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  private pointAt(p: { x: number; y: number }, snap: boolean): DPoint | null {
    const price = this.host.coordinateToPrice(p.y);
    const l = this.host.coordinateToLogical(p.x);
    if (price === null || l === null) return null;
    const times = this.prim.times; const barMs = this.prim.barMs;
    let t = logicalToTime(times, barMs, l);
    let out = price;
    if (snap && this.magnetOn) {
      const i = Math.round(l);
      const bar = i >= 0 && i < this.prim.bars.length ? this.prim.bars[i] : null;
      if (bar) {
        const y0 = this.host.coordinateToPrice(p.y - 12); const y1 = this.host.coordinateToPrice(p.y + 12);
        const reach = y0 !== null && y1 !== null ? Math.abs(y0 - y1) / 2 : 0;
        const snapped = magnet(price, bar, reach);
        if (snapped !== price) { out = snapped; t = bar.t; }
      }
    }
    return { t, p: out };
  }

  private readonly onKey = (e: KeyboardEvent): void => {
    const tag = (e.target as HTMLElement | null)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === 'Escape') { if (this.tool) this.setTool(null); else if (this.prim.selectedId) { this.prim.selectedId = null; this.render(); } return; }
    if ((e.key === 'Delete' || e.key === 'Backspace') && this.prim.selectedId) { e.preventDefault(); this.removeSelected(); return; }
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      const k: Record<string, DrawKind> = { t: 'trend', h: 'hline', j: 'hray', v: 'vline', r: 'rect', b: 'bookmark' };
      const kind = k[e.key.toLowerCase()];
      if (kind) { e.preventDefault(); this.setTool(kind); }
    }
  };

  private readonly onHover = (e: PointerEvent): void => {
    if (!this.pane || this.drag || this.host.busy()) return;
    const p = this.local(e);
    if (!p) return;
    if (this.tool) {
      this.pane.style.cursor = 'crosshair';
      if (this.first) {
        const pt = this.pointAt(p, true);
        if (pt) { this.prim.preview = { id: 'preview', kind: this.tool, a: this.first, b: pt, color: this.store.color }; this.prim.update(); }
      }
      return;
    }
    const hit = this.prim.hit(p.x, p.y);
    const book = hit && this.store.drawings.find((x) => x.id === hit.id)?.kind === 'bookmark' ? hit.id : null;
    this.pane.style.cursor = book ? 'ns-resize' : hit ? (hit.part === 'body' ? 'move' : 'grab') : '';
    if (book !== this.prim.cardId) { this.prim.cardId = book; this.prim.update(); }
  };

  private readonly onDown = (e: PointerEvent): void => {
    if (e.button !== 0 || this.host.busy()) return;
    const p = this.local(e);
    if (!p) return;
    if (this.tool) {
      const pt = this.pointAt(p, true);
      if (!pt) return;
      e.stopPropagation(); e.preventDefault();
      const kind = this.tool;
      if (TWO_POINT.includes(kind) && !this.first) { this.first = pt; return; }
      let text: string | undefined;
      if (kind === 'text') {
        const typed = window.prompt('Note text', '');
        if (!typed) { this.setTool(null); return; }
        text = typed;
      }
      if (kind === 'bookmark') pt.p = Math.round(pt.p * 4) / 4;   // to the 0.25 tick
      const color = kind === 'bookmark' ? BOOKMARK_COLOR : this.store.color;
      const d: Drawing = { id: newId(), kind, a: this.first ?? pt, color, ...(kind === 'bookmark' ? { dashed: true } : {}), ...(this.first ? { b: pt } : {}), ...(text ? { text } : {}) };
      this.store.drawings.push(d);
      this.prim.selectedId = d.id;
      this.setTool(null);
      this.save();
      return;
    }
    const hit = this.prim.hit(p.x, p.y);
    if (!hit) { if (this.prim.selectedId) { this.prim.selectedId = null; this.render(); } return; }
    e.stopPropagation(); e.preventDefault();
    this.prim.selectedId = hit.id;
    const d = this.selected();
    const start = this.pointAt(p, false);
    if (!d || !start) { this.render(); return; }
    this.drag = { id: d.id, part: hit.part, start, a: { ...d.a }, ...(d.b ? { b: { ...d.b } } : {}) };
    this.host.setDragScroll(false);
    window.addEventListener('pointermove', this.onDrag);
    window.addEventListener('pointerup', this.endDrag);
    window.addEventListener('pointercancel', this.endDrag);
    this.render();
  };

  private readonly onDrag = (e: PointerEvent): void => {
    const g = this.drag;
    if (!g) return;
    const d = this.store.drawings.find((x) => x.id === g.id);
    const p = this.local(e);
    if (!d || !p) return;
    if (d.kind === 'bookmark') {
      // a bookmark only moves up and down; its card shows while dragging
      const price = this.host.coordinateToPrice(p.y);
      if (price === null) return;
      d.a = { t: g.a.t, p: Math.round(price * 4) / 4 };
      this.prim.cardId = d.id;
    } else if (g.part === 'body') {
      const now = this.pointAt(p, false);
      if (!now) return;
      const dt = now.t - g.start.t; const dp = now.p - g.start.p;
      d.a = { t: g.a.t + dt, p: g.a.p + dp };
      if (g.b) d.b = { t: g.b.t + dt, p: g.b.p + dp };
    } else {
      const pt = this.pointAt(p, true);
      if (!pt) return;
      d[g.part] = pt;
    }
    this.render();
  };

  private readonly endDrag = (): void => {
    if (!this.drag) return;
    this.drag = null;
    window.removeEventListener('pointermove', this.onDrag);
    window.removeEventListener('pointerup', this.endDrag);
    window.removeEventListener('pointercancel', this.endDrag);
    this.host.setDragScroll(this.tool === null);
    this.save();
  };

  /** Double-click a text note to change it. */
  private readonly onDouble = (e: MouseEvent): void => {
    const p = this.local(e);
    if (!p || this.tool) return;
    const hit = this.prim.hit(p.x, p.y);
    const d = hit ? this.store.drawings.find((x) => x.id === hit.id) : null;
    if (d?.kind === 'bookmark') { this.prim.selectedId = d.id; this.prim.cardId = null; this.removeSelected(); return; }
    if (d?.kind !== 'text') return;
    const typed = window.prompt('Note text', d.text ?? '');
    if (typed !== null) { d.text = typed; this.save(); }
  };
}
