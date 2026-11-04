import type { ManagedSeriesApi } from './ChartManager';
import { resolveContractSpec, type BrokerSymbolSpec, type ContractSpec } from './contractSpecs';
import {
  buildPositionModel,
  createPosition,
  flipSide,
  moveHandle,
  type PositionHandle,
  type PositionModel,
  type PositionSide,
  type PositionToolState,
} from './positionTool';
import { PositionToolPrimitive } from './positionToolPrimitive';
import { getStoredState, setStoredState } from '@/utils/localStorage';

export interface PositionToolHost {
  /** The candlestick series the plan is drawn on. */
  getSeries(): ManagedSeriesApi | null;
  coordinateToPrice(y: number): number | null;
  coordinateToTime(x: number): number | null;
  recentBars(): readonly { high: number; low: number }[];
  setDragScroll(enabled: boolean): void;
  /** Called when the plan or its numbers change, for the info card. */
  onChange(state: PositionToolState | null, model: PositionModel | null, spec: ContractSpec): void;
  /** Called after a plan is placed, so the chart can go back to pan mode. */
  onPlaced(): void;
}

const storageKey = (symbol: string): string => `algotrader_position_tool:${symbol}`;
const pointValueKey = (symbol: string): string => `algotrader_point_value:${symbol}`;

/**
 * Owns the risk-to-reward tool on one chart: placing it on click in long / short mode,
 * dragging its entry, stop and target lines, and keeping it per symbol.
 */
export class PositionToolController {
  private readonly primitive = new PositionToolPrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private pane: HTMLElement | null = null;
  private state: PositionToolState | null = null;
  private symbol: string | null = null;
  private minMove: number | null = null;
  private broker: BrokerSymbolSpec | null = null;
  private customPointValue: number | null = null;
  private placing: PositionSide | null = null;
  private dragging: PositionHandle | null = null;

  constructor(private readonly host: PositionToolHost) {}

  get spec(): ContractSpec {
    return resolveContractSpec({ symbol: this.symbol, minMove: this.minMove, broker: this.broker, customPointValue: this.customPointValue });
  }

  setMarket(symbol: string | null, minMove: number | null): void {
    if (symbol === this.symbol && minMove === this.minMove) return;
    const sameSymbol = symbol === this.symbol;
    this.symbol = symbol;
    this.minMove = minMove;
    if (sameSymbol) {
      this.render();
      return;
    }
    this.broker = null;
    this.customPointValue = symbol ? getStoredState<number>(pointValueKey(symbol)) : null;
    this.state = symbol ? getStoredState<PositionToolState>(storageKey(symbol)) : null;
    this.render();
  }

  setBrokerSpec(symbol: string, spec: BrokerSymbolSpec | null): void {
    if (symbol !== this.symbol) return;
    this.broker = spec;
    this.render();
  }

  setCustomPointValue(value: number | null): void {
    this.customPointValue = value && value > 0 ? value : null;
    if (this.symbol) setStoredState(pointValueKey(this.symbol), this.customPointValue);
    this.render();
  }

  /** Long / short mode: the next click on the chart places a plan. */
  setPlacing(side: PositionSide | null): void {
    this.placing = side;
  }

  setPane(pane: HTMLElement | null): void {
    if (this.pane === pane) return;
    this.pane?.removeEventListener('pointerdown', this.onPointerDown, true);
    this.pane?.removeEventListener('pointermove', this.onHover);
    this.pane = pane;
    pane?.addEventListener('pointerdown', this.onPointerDown, true);
    pane?.addEventListener('pointermove', this.onHover);
  }

  /** Re-attach after the price series is recreated. */
  syncSeries(): void {
    const series = this.host.getSeries();
    if (series === this.attachedTo) return;
    try {
      this.attachedTo?.detachPrimitive(this.primitive);
    } catch {
      // The old series is already gone.
    }
    this.attachedTo = series;
    // Test doubles of the series may not implement primitives.
    series?.attachPrimitive?.(this.primitive);
    this.render();
  }

  update(patch: Partial<PositionToolState>): void {
    if (!this.state) return;
    this.state = { ...this.state, ...patch, qty: Math.max(1, Math.round(patch.qty ?? this.state.qty)) };
    this.save();
  }

  flip(): void {
    if (!this.state) return;
    this.state = flipSide(this.state, this.spec.tickSize);
    this.save();
  }

  remove(): void {
    this.state = null;
    this.save();
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
    if (this.symbol) setStoredState(storageKey(this.symbol), this.state);
    this.render();
  }

  private render(): void {
    const spec = this.spec;
    const model = this.state ? buildPositionModel(this.state, spec) : null;
    this.primitive.set(this.state, model);
    this.host.onChange(this.state, model, spec);
  }

  private local(event: PointerEvent): { x: number; y: number } | null {
    if (!this.pane) return null;
    const r = this.pane.getBoundingClientRect();
    return { x: event.clientX - r.left, y: event.clientY - r.top };
  }

  private readonly onHover = (event: PointerEvent): void => {
    if (!this.pane || this.dragging) return;
    const p = this.local(event);
    const close = p ? this.primitive.hitClose(p.x, p.y) : false;
    const over = p ? this.primitive.hit(p.y) : null;
    this.pane.style.cursor = close ? 'pointer' : over ? 'ns-resize' : this.placing ? 'crosshair' : '';
  };

  private readonly onPointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    const p = this.local(event);
    if (!p) return;
    if (this.placing) {
      const price = this.host.coordinateToPrice(p.y);
      const time = this.host.coordinateToTime(p.x);
      if (price === null || time === null) return;
      this.state = createPosition(this.placing, price, time, this.host.recentBars(), this.spec.tickSize);
      this.placing = null;
      event.stopPropagation();
      event.preventDefault();
      this.save();
      this.host.onPlaced();
      return;
    }
    if (this.state && this.primitive.hitClose(p.x, p.y)) {
      event.stopPropagation();
      event.preventDefault();
      this.remove();
      return;
    }
    const handle = this.primitive.hit(p.y);
    if (!handle) return;
    // Capture phase on the pane: the chart never sees this press, so it doesn't pan.
    event.stopPropagation();
    event.preventDefault();
    this.dragging = handle;
    this.host.setDragScroll(false);
    window.addEventListener('pointermove', this.onDrag);
    window.addEventListener('pointerup', this.endDrag);
    window.addEventListener('pointercancel', this.endDrag);
  };

  private readonly onDrag = (event: PointerEvent): void => {
    if (!this.dragging || !this.state) return;
    const p = this.local(event);
    const price = p ? this.host.coordinateToPrice(p.y) : null;
    if (price === null) return;
    this.state = moveHandle(this.state, this.dragging, price, this.spec.tickSize);
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
