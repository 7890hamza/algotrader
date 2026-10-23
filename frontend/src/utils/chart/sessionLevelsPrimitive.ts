import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  AutoscaleInfo,
  Coordinate,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  Logical,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

import {
  firstTouchTime,
  formatLevelPrice,
  type LevelCandle,
  type SessionLevelSegment,
} from './sessionLevels';

const LABEL_GAP_PX = 8;
const LABEL_FONT = '600 12px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const TOUCH_RADIUS_PX = 4;
const TOUCH_FILL = '#131722';
const EMPTY_PANE_VIEWS: readonly IPrimitivePaneView[] = [];

interface DrawableSegment {
  segment: SessionLevelSegment;
  startX: number;
  endX: number;
  y: number;
  touchX: number | null;
}

function crisp(value: number): number {
  return Math.round(value) + 0.5;
}

function dashFor(lineStyle: number, lineWidth: number): number[] {
  if (lineStyle === 1) return [2 * lineWidth, 3 * lineWidth];
  if (lineStyle === 2) return [4, 4];
  if (lineStyle === 3) return [8, 6];
  return [];
}

class SessionLevelsRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly drawables: readonly DrawableSegment[],
    private readonly precision: number,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      context.save();
      context.lineCap = 'butt';
      context.font = LABEL_FONT;
      context.textBaseline = 'middle';

      // Labels sit right of the line end; while a session's end is still off to the
      // right they pin to the pane edge and the line stops just before them.
      const placed = this.drawables.map((drawable) => {
        const { segment, endX } = drawable;
        const text = segment.showPrice
          ? `${segment.label} ${formatLevelPrice(segment.price, this.precision)}`
          : segment.label;
        const maxLabelX = mediaSize.width - context.measureText(text).width - LABEL_GAP_PX;
        const labelX = Math.min(endX + LABEL_GAP_PX, maxLabelX);
        return { ...drawable, text, labelX, lineEndX: Math.min(endX, labelX - LABEL_GAP_PX / 2) };
      });

      for (const { segment, startX, lineEndX, y } of placed) {
        if (lineEndX <= startX) continue;
        context.beginPath();
        context.strokeStyle = segment.color;
        context.lineWidth = segment.lineWidth;
        context.setLineDash(dashFor(segment.lineStyle, segment.lineWidth));
        context.moveTo(Math.round(startX), crisp(y));
        context.lineTo(Math.round(lineEndX), crisp(y));
        context.stroke();
      }

      context.setLineDash([]);
      for (const { segment, y, touchX, text, labelX } of placed) {
        if (touchX !== null) {
          context.beginPath();
          context.arc(touchX, y, TOUCH_RADIUS_PX, 0, Math.PI * 2);
          context.fillStyle = TOUCH_FILL;
          context.fill();
          context.lineWidth = 1.5;
          context.strokeStyle = segment.color;
          context.stroke();
        }
        context.fillStyle = segment.labelColor;
        context.fillText(text, labelX, y);
      }

      context.restore();
    });
  }
}

class SessionLevelsPaneView implements IPrimitivePaneView {
  constructor(private readonly primitive: SessionLevelsPrimitive) {}

  zOrder(): PrimitivePaneViewZOrder {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer | null {
    return this.primitive.createRenderer();
  }
}

/**
 * Draws session levels as crisp horizontal segments with a price label at the
 * right end of each and a circle on the first candle that touched the level.
 */
export class SessionLevelsPrimitive implements ISeriesPrimitive<Time> {
  private readonly paneView = new SessionLevelsPaneView(this);
  private readonly paneViewsList: readonly IPrimitivePaneView[] = [this.paneView];
  private attachedParams: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private segments: SessionLevelSegment[];
  private precision = 2;

  constructor(segments: readonly SessionLevelSegment[] = []) {
    this.segments = [...segments];
  }

  setSegments(segments: readonly SessionLevelSegment[]): void {
    this.segments = [...segments];
    this.attachedParams?.requestUpdate();
  }

  getSegments(): readonly SessionLevelSegment[] {
    return this.segments;
  }

  setPrecision(precision: number): void {
    this.precision = Math.max(0, Math.min(8, Math.round(precision)));
    this.attachedParams?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.attachedParams = param;
  }

  detached(): void {
    this.attachedParams = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.segments.length > 0 ? this.paneViewsList : EMPTY_PANE_VIEWS;
  }

  autoscaleInfo(startTimePoint: Logical, endTimePoint: Logical): AutoscaleInfo | null {
    const visible = this.segments.filter((segment) =>
      this.intersectsLogicalRange(segment, startTimePoint, endTimePoint),
    );
    if (visible.length === 0) return null;
    const prices = visible.map((segment) => segment.price);
    return { priceRange: { minValue: Math.min(...prices), maxValue: Math.max(...prices) } };
  }

  createRenderer(): IPrimitivePaneRenderer | null {
    const params = this.attachedParams;
    if (!params || this.segments.length === 0) return null;

    const candles = this.candles();
    const drawables: DrawableSegment[] = [];
    for (const segment of this.segments) {
      const startX = this.timeToX(segment.startTime);
      const lastBarX = this.timeToX(segment.endTime);
      const windowEndX =
        segment.sessionEndTime !== null && segment.sessionEndTime > segment.endTime
          ? this.futureTimeToX(segment.endTime, segment.sessionEndTime)
          : null;
      const endX =
        lastBarX === null ? null : Math.max(Number(lastBarX), Number(windowEndX ?? lastBarX));
      const y = params.series.priceToCoordinate(segment.price);
      if (startX === null || endX === null || y === null) continue;
      const touchTime = firstTouchTime(segment, candles);
      const touchX = touchTime === null ? null : this.timeToX(touchTime);
      drawables.push({ segment, startX, endX, y, touchX });
    }
    return drawables.length > 0 ? new SessionLevelsRenderer(drawables, this.precision) : null;
  }

  private candles(): LevelCandle[] {
    const series = this.attachedParams?.series;
    if (!series) return [];
    const out: LevelCandle[] = [];
    for (const item of series.data()) {
      const record = item as { time?: unknown; high?: unknown; low?: unknown };
      if (
        typeof record.time === 'number' &&
        typeof record.high === 'number' &&
        typeof record.low === 'number'
      ) {
        out.push({ time: record.time, high: record.high, low: record.low });
      }
    }
    return out;
  }

  /**
   * x for a time after the last loaded bar (the rest of a live session),
   * extrapolated at one bar per bar interval from the series' last bar.
   */
  private futureTimeToX(lastSegmentTime: number, time: number): number | null {
    const params = this.attachedParams;
    if (!params) return null;
    const timeScale = params.chart.timeScale();
    const exact = timeScale.timeToCoordinate(time as Time);
    if (exact !== null) return Number(exact);
    const data = params.series.data();
    if (data.length < 2) return null;
    const lastTime = Number(data[data.length - 1].time);
    const prevTime = Number(data[data.length - 2].time);
    const bar = lastTime - prevTime;
    if (!(bar > 0) || time <= lastTime || lastSegmentTime < prevTime) return null;
    const lastIndex = timeScale.timeToIndex(lastTime as Time, false);
    if (lastIndex === null) return null;
    const logical = Number(lastIndex) + (time - lastTime) / bar;
    const x = timeScale.logicalToCoordinate(logical as Logical);
    return x === null ? null : Number(x);
  }

  private timeToX(time: number): Coordinate | null {
    const timeScale = this.attachedParams?.chart.timeScale();
    if (!timeScale) return null;
    const exact = timeScale.timeToCoordinate(time as Time);
    if (exact !== null) return exact;
    const nearest = timeScale.timeToIndex(time as Time, true);
    return nearest === null ? null : timeScale.logicalToCoordinate(nearest as unknown as Logical);
  }

  private intersectsLogicalRange(
    segment: SessionLevelSegment,
    start: Logical,
    end: Logical,
  ): boolean {
    const timeScale = this.attachedParams?.chart.timeScale();
    if (!timeScale) return false;
    const first = timeScale.timeToIndex(segment.startTime as Time, true);
    const last = timeScale.timeToIndex(segment.endTime as Time, true);
    if (first === null || last === null) return false;
    return Number(last) >= Number(start) && Number(first) <= Number(end);
  }
}
