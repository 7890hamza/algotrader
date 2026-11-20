import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time } from 'lightweight-charts';

/**
 * Replay: covers everything to the right of the last bar shown, so indicator lines, levels and
 * trades from later in the week stay hidden until playback gets there.
 */
export class ReplayCurtainPrimitive implements ISeriesPrimitive<Time> {
  private param: SeriesAttachedParameter<Time> | null = null;
  private lastTime: number | null = null;

  constructor(private readonly color: string) {}

  attached(param: SeriesAttachedParameter<Time>): void { this.param = param; }
  detached(): void { this.param = null; }

  setLastTime(sec: number | null): void {
    this.lastTime = sec;
    this.param?.requestUpdate();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = {
      draw: (target) => {
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
          const p = this.param;
          if (!p || this.lastTime === null) return;
          const ts = p.chart.timeScale();
          const x = ts.timeToCoordinate(this.lastTime as Time);
          if (x === null) return;
          const left = x + Math.max(2, ts.options().barSpacing / 2) + 1;
          if (left >= mediaSize.width) return;
          ctx.fillStyle = this.color;
          ctx.fillRect(left, 0, mediaSize.width - left, mediaSize.height);
          ctx.strokeStyle = 'rgba(227, 173, 66, 0.8)';
          ctx.setLineDash([4, 4]);
          ctx.beginPath(); ctx.moveTo(Math.round(left) + 0.5, 0); ctx.lineTo(Math.round(left) + 0.5, mediaSize.height); ctx.stroke();
          ctx.setLineDash([]);
        });
      },
    };
    return [{ zOrder: () => 'top', renderer: () => renderer }];
  }
}
