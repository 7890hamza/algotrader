import { watch, type WatchStopHandle } from 'vue';

import { useGamePlanStore } from '@/stores/gamePlanStore';

import type { ManagedSeriesApi } from './ChartManager';
import { GamePlanPrimitive } from './gamePlanPrimitive';

/**
 * Keeps the Game Plan lines on one chart: follows the store's plan while the panel is shown and
 * moves "now" along with the chart's last candle.
 */
export class GamePlanChartLink {
  private readonly primitive = new GamePlanPrimitive();
  private attachedTo: ManagedSeriesApi | null = null;
  private stop: WatchStopHandle | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly host: {
      getSeries(): ManagedSeriesApi | null;
      getSymbol(): string | null;
      lastBar(): { t: number; close: number } | null;
    },
  ) {
    const store = useGamePlanStore();
    this.stop = watch(() => [store.plan, store.visible] as const, () => this.render(), { immediate: true });
    this.timer = setInterval(() => this.render(), 2000);
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

  private render(): void {
    const store = useGamePlanStore();
    const plan = store.visible ? store.plan : null;
    if (!plan || plan.symbol !== this.host.getSymbol()) {
      this.primitive.set(null, 0);
      return;
    }
    let t = plan.last?.t ?? plan.start;
    let price = plan.last?.close ?? 0;
    const bar = this.host.lastBar();
    if (bar && bar.t >= t && bar.t < plan.end) {
      t = bar.t;
      price = bar.close;
    }
    this.primitive.set(plan, t, price);
  }

  destroy(): void {
    this.stop?.();
    if (this.timer) clearInterval(this.timer);
    try {
      this.attachedTo?.detachPrimitive(this.primitive);
    } catch {
      // Already detached.
    }
    this.attachedTo = null;
  }
}
