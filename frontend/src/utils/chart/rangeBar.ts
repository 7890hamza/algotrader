import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';

import type { IndicatorDataPoint, JsonObject } from '@/types/contracts';

/** MTF SDEV's day-range bar: today's high to low as a vertical bar at the chart's right edge. */
export interface RangeBar {
  /** Epoch seconds of the last bar the range belongs to. */
  time: number;
  high: number;
  low: number;
  mid: number;
  /** Average daily range, or null while there isn't enough history. */
  adr: number | null;
  color: string;
}

const num = (point: IndicatorDataPoint | undefined, key: string): number | null => {
  const value = point?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

/** The bar for the running day, from MTF SDEV's dr_h / dr_l / dr_mid / adr outputs. */
export function buildRangeBar(points: readonly IndicatorDataPoint[], guide: JsonObject | undefined): RangeBar | null {
  if (!guide || guide.kind !== 'mtf_sdev' || !points.length) return null;
  let last: IndicatorDataPoint | undefined;
  for (const p of points) if (!last || Number(p.timestamp_ms) > Number(last.timestamp_ms)) last = p;
  const high = num(last, 'dr_h');
  const low = num(last, 'dr_l');
  if (!last || high === null || low === null) return null;
  const color = typeof guide.rangeColor === 'string' ? guide.rangeColor : '#378ADD';
  return { time: Math.floor(Number(last.timestamp_ms) / 1000), high, low, mid: num(last, 'dr_mid') ?? (high + low) / 2, adr: num(last, 'adr'), color };
}

export interface DrawnRangeBar {
  bar: RangeBar;
  yHigh: number;
  yLow: number;
  yMid: number;
  /** Faint track: how far a normal-sized day could still reach (low + ADR, high - ADR). */
  yTrackTop: number | null;
  yTrackBottom: number | null;
}

const FONT = '500 11px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const WIDTH = 10;

export class RangeBarRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly d: DrawnRangeBar) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const { bar, yHigh, yLow, yMid, yTrackTop, yTrackBottom } = this.d;
      // Pinned to the pane's right edge, clear of the line labels at the end of each level.
      const x = mediaSize.width - WIDTH - 10;
      ctx.save();
      if (yTrackTop !== null && yTrackBottom !== null) {
        ctx.fillStyle = 'rgba(139, 148, 158, 0.16)';
        ctx.fillRect(x, yTrackTop, WIDTH, yTrackBottom - yTrackTop);
      }
      ctx.fillStyle = bar.color;
      ctx.globalAlpha = 0.85;
      ctx.fillRect(x, yHigh, WIDTH, Math.max(2, yLow - yHigh));
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#e6e6e6';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x - 4, Math.round(yMid) + 0.5);
      ctx.lineTo(x + WIDTH + 4, Math.round(yMid) + 0.5);
      ctx.stroke();
      ctx.font = FONT;
      ctx.textBaseline = 'middle';
      ctx.fillStyle = bar.color;
      ctx.textAlign = 'right';
      ctx.fillText('50% DR', x - 7, yMid);
      if (bar.adr) {
        const used = Math.round(((bar.high - bar.low) / bar.adr) * 100);
        ctx.fillStyle = '#9aa4b2';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(`${used}%`, x + WIDTH / 2, (yTrackTop ?? yHigh) - 4);
      }
      ctx.restore();
    });
  }
}
