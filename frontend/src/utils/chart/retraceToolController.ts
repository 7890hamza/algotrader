import type { ManagedSeriesApi } from './ChartManager';
import { clampPct, newRetrace, parseLevels, snapToCandle, type RetraceAnchor, type RetraceDrawing } from './retraceTool';
import { RetraceToolPrimitive } from './retraceToolPrimitive';
import { getStoredState, setStoredState } from '@/utils/localStorage';

export interface RetraceToolHost {
  getSeries(): ManagedSeriesApi | null;
  coordinateToPrice(y: number): number | null;
  coordinateToTime(x: number): number | null;
  /** The candle at a time, for snapping anchors to its high / low. */
  barAt(time: number): { high: number; low: number } | null;
  setDragScroll(enabled: boolean): void;
  onChange(drawings: readonly RetraceDrawing[], selected: RetraceDrawing | null): void;
  /** The second anchor was placed: the chart can go back to pan mode. */
  onPlaced(): void;
}

interface Stored {
  drawings: RetraceDrawing[];
  /** The zone and lines new drawings start with (your last edit). */
  zone: [number, number];
  lines: number[];
}

const storageKey = (symbol: string): string => `algotrader_retrace:${symbol}`;

/**
 * Owns the Retrace tool on one chart: in retrace mode the first click sets the leg's start, the
 * second its end (both snap to the candle's high or low). Anchors can be dragged; the selected
 * drawing shows a remove button and its settings card. Drawings are kept per symbol.
 */
export class RetraceToolController {
  private readonly primitive = new RetraceToolPrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private pane: HTMLElement | null = null;
  private symbol: string | null = null;
  private store: Stored = { drawings: [], zone: [40, 60], lines: [50] };
  private selectedId: string | null = null;
  private placing = false;
  private pending: RetraceAnchor | null = null;
  private cursor: { x: number; y: number } | null = null;
  private dragging: { id: string; part: 'a' | 'b' } | null = null;
  snap = true;

  constructor(private readonly host: RetraceToolHost) {}

  setSymbol(symbol: string | null): void {
    if (symbol === this.symbol) return;
    this.symbol = symbol;
    const saved = symbol ? getStoredState<Stored>(storageKey(symbol)) : null;
    this.store = saved && Array.isArray(saved.drawings) ? saved : { drawings: [], zone: [40, 60], lines: [50] };
    this.selectedId = null;
    this.pending = null;
    this.render();
  }

  setPlacing(on: boolean): void {
    this.placing = on;
    if (!on) this.pending = null;
    this.render();
  }

  setPane(pane: HTMLElement | null): void {
    if (this.pane === pane) return;
    this.pane?.removeEventListener('pointerdown', this.onPointerDown, true);
    this.pane?.removeEventListener('pointermove', this.onHover);
    this.pane = pane;
    pane?.addEventListener('pointerdown', this.onPointerDown, true);
    pane?.addEventListener('pointermove', this.onHover);
  }

  syncSeries(): void {
    const series = this.host.getSeries();
    if (series === this.attachedTo) return;
    try {
      this.attachedTo?.detachPrimitive(this.primitive);
    } catch {
      // The old series is already gone.
    }
    this.attachedTo = series;
    series?.attachPrimitive?.(this.primitive);
    this.render();
  }

  /** Change the selected drawing's zone edges / extra lines (also the default for new ones). */
  updateSelected(patch: { from?: number; to?: number; lines?: string }): void {
    const d = this.store.drawings.find((x) => x.id === this.selectedId);
    if (!d) return;
    if (patch.from !== undefined && Number.isFinite(patch.from)) d.from = clampPct(patch.from);
    if (patch.to !== undefined && Number.isFinite(patch.to)) d.to = clampPct(patch.to);
    if (patch.lines !== undefined) d.lines = parseLevels(patch.lines);
    this.store.zone = [d.from, d.to];
    this.store.lines = [...d.lines];
    this.save();
  }

  removeSelected(): void {
    this.store.drawings = this.store.drawings.filter((d) => d.id !== this.selectedId);
    this.selectedId = null;
    this.save();
  }

  removeAll(): void {
    this.store.drawings = [];
    this.selectedId = null;
    this.save();
  }

  deselect(): void {
    this.selectedId = null;
    this.render();
  }

  destroy(): void {
    this.setPane(null);
    this.endDrag();
    try {
      this.attachedTo?.detachPrimitive(this.primitive);
    } catch {
      // Already detached.
    }
    this.attachedTo = null;
  }

  private save(): void {
    if (this.symbol) setStoredState(storageKey(this.symbol), this.store);
    this.render();
  }

  private render(): void {
    this.primitive.set(this.store.drawings, this.selectedId, this.pending, this.pending ? this.cursor : null);
    this.host.onChange(this.store.drawings, this.store.drawings.find((d) => d.id === this.selectedId) ?? null);
  }

  private local(event: PointerEvent): { x: number; y: number } | null {
    if (!this.pane) return null;
    const r = this.pane.getBoundingClientRect();
    return { x: event.clientX - r.left, y: event.clientY - r.top };
  }

  private anchorAt(p: { x: number; y: number }): RetraceAnchor | null {
    const price = this.host.coordinateToPrice(p.y);
    const time = this.host.coordinateToTime(p.x);
    if (price === null || time === null) return null;
    return { time, price: this.snap ? snapToCandle(price, this.host.barAt(time)) : price };
  }

  private readonly onHover = (event: PointerEvent): void => {
    if (!this.pane || this.dragging) return;
    const p = this.local(event);
    if (!p) return;
    if (this.pending) {
      this.cursor = p;
      this.render();
    }
    const hit = this.primitive.hit(p.x, p.y);
    if (this.placing) this.pane.style.cursor = 'crosshair';
    else if (hit?.part === 'close') this.pane.style.cursor = 'pointer';
    else if (hit?.part === 'a' || hit?.part === 'b') this.pane.style.cursor = 'grab';
  };

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    const p = this.local(event);
    if (!p) return;
    if (this.placing) {
      const anchor = this.anchorAt(p);
      if (!anchor) return;
      event.stopPropagation();
      event.preventDefault();
      if (!this.pending) {
        this.pending = anchor;
        this.cursor = p;
        this.render();
        return;
      }
      const d = newRetrace(this.pending, anchor, this.store.zone, this.store.lines);
      this.store.drawings.push(d);
      this.selectedId = d.id;
      this.pending = null;
      this.placing = false;
      this.save();
      this.host.onPlaced();
      return;
    }
    const hit = this.primitive.hit(p.x, p.y);
    if (!hit) {
      if (this.selectedId) this.deselect();
      return;
    }
    if (hit.part === 'close') {
      event.stopPropagation();
      event.preventDefault();
      this.selectedId = hit.id;
      this.removeSelected();
      return;
    }
    this.selectedId = hit.id;
    if (hit.part === 'body') {
      this.render(); // select only; the chart still pans
      return;
    }
    event.stopPropagation();
    event.preventDefault();
    this.dragging = { id: hit.id, part: hit.part };
    this.host.setDragScroll(false);
    window.addEventListener('pointermove', this.onDrag);
    window.addEventListener('pointerup', this.endDrag);
    window.addEventListener('pointercancel', this.endDrag);
    this.render();
  };

  private readonly onDrag = (event: PointerEvent): void => {
    if (!this.dragging) return;
    const d = this.store.drawings.find((x) => x.id === this.dragging!.id);
    const p = this.local(event);
    const anchor = p ? this.anchorAt(p) : null;
    if (!d || !anchor) return;
    d[this.dragging.part] = anchor;
    this.render();
  };

  private readonly endDrag = (): void => {
    if (!this.dragging) return;
    this.dragging = null;
    window.removeEventListener('pointermove', this.onDrag);
    window.removeEventListener('pointerup', this.endDrag);
    window.removeEventListener('pointercancel', this.endDrag);
    this.host.setDragScroll(true);
    this.save();
  };
}
