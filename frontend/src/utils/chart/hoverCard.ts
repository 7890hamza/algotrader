import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';

const FONT = '12px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const BOLD = '600 12px -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
const LINE_H = 17;
const MAX_W = 360;

function wrap(ctx: CanvasRenderingContext2D, text: string): string[] {
  const words = text.split(' ');
  const out: string[] = [];
  let line = '';
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (ctx.measureText(next).width > MAX_W - 20 && line) {
      out.push(line);
      line = w;
    } else line = next;
  }
  if (line) out.push(line);
  return out;
}

/** A plain-language card next to the cursor for the hovered line or box (Breaks). */
export class HoverCardRenderer implements IPrimitivePaneRenderer {
  constructor(private readonly lines: readonly string[], private readonly x: number, private readonly y: number) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      const rows: { text: string; head: boolean }[] = [];
      this.lines.forEach((l, i) => {
        ctx.font = i ? FONT : BOLD;
        for (const part of wrap(ctx, l)) rows.push({ text: part, head: i === 0 });
      });
      const width = Math.min(MAX_W, Math.max(...rows.map((r) => { ctx.font = r.head ? BOLD : FONT; return ctx.measureText(r.text).width; })) + 20);
      const height = rows.length * LINE_H + 12;
      const left = Math.max(4, Math.min(mediaSize.width - width - 4, this.x + 14));
      const top = this.y - height - 12 >= 4 ? this.y - height - 12 : Math.min(mediaSize.height - height - 4, this.y + 14);
      ctx.beginPath();
      ctx.roundRect(left, top, width, height, 6);
      ctx.fillStyle = 'rgba(19, 23, 34, 0.96)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
      ctx.stroke();
      ctx.textBaseline = 'middle';
      rows.forEach((r, i) => {
        ctx.font = r.head ? BOLD : FONT;
        ctx.fillStyle = r.head ? '#e6e6e6' : '#9aa4b2';
        ctx.fillText(r.text, left + 10, top + 6 + LINE_H * i + LINE_H / 2);
      });
      ctx.restore();
    });
  }
}
