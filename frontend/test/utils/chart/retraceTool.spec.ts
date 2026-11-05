import { beforeEach, describe, expect, it, vi } from 'vitest';

import { buildRetraceModel, newRetrace, parseLevels, retracePrice, snapToCandle } from '@/utils/chart/retraceTool';
import { RetraceToolController, type RetraceToolHost } from '@/utils/chart/retraceToolController';

describe('retrace math', () => {
  it('measures back from the second anchor toward the first', () => {
    const up = newRetrace({ time: 1, price: 7680 }, { time: 2, price: 7740 });
    expect(retracePrice(up, 40)).toBe(7716);
    expect(retracePrice(up, 60)).toBe(7704);
    const m = buildRetraceModel(up);
    expect(m).toMatchObject({ up: true, range: 60, zoneHigh: 7716, zoneLow: 7704 });
    expect(m.levels.map((l) => l.pct)).toEqual([0, 40, 50, 60, 100]);
    const down = newRetrace({ time: 1, price: 7740 }, { time: 2, price: 7680 }, [50, 61.8], []);
    expect(buildRetraceModel(down)).toMatchObject({ up: false, zoneLow: 7710, zoneHigh: 7717.08 });
    expect(retracePrice(up, 127)).toBeCloseTo(7663.8); // past the first anchor
  });

  it('parses extra lines and snaps to the nearer candle extreme', () => {
    expect(parseLevels('50, 100%; -27  x 999')).toEqual([50, 100, -27]);
    expect(snapToCandle(7701, { high: 7702, low: 7690 })).toBe(7702);
    expect(snapToCandle(7693, { high: 7702, low: 7690 })).toBe(7690);
    expect(snapToCandle(7693, null)).toBe(7693);
  });
});

function host(): RetraceToolHost {
  return {
    getSeries: () => null,
    coordinateToPrice: (y) => 7800 - y,
    coordinateToTime: (x) => 1000 + x,
    barAt: () => null,
    setDragScroll: vi.fn(),
    onChange: vi.fn(),
    onPlaced: vi.fn(),
  };
}

describe('RetraceToolController', () => {
  beforeEach(() => localStorage.clear());

  it('places a retrace with two clicks, edits it, and keeps it per symbol', () => {
    const h = host();
    const c = new RetraceToolController(h);
    const pane = document.createElement('div');
    const below = vi.fn();
    pane.appendChild(document.createElement('canvas')).addEventListener('pointerdown', below);
    c.setPane(pane);
    c.setSymbol('ES');
    c.setPlacing(true);
    const click = (x: number, y: number): void => {
      pane.querySelector('canvas')!.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: x, clientY: y }));
    };
    click(10, 120); // 7680
    expect(h.onPlaced).not.toHaveBeenCalled();
    click(50, 60); // 7740
    expect(below).not.toHaveBeenCalled();
    expect(h.onPlaced).toHaveBeenCalled();
    const [drawings, selected] = vi.mocked(h.onChange).mock.calls.at(-1)!;
    expect(drawings).toHaveLength(1);
    expect(selected).toMatchObject({ a: { time: 1010, price: 7680 }, b: { time: 1050, price: 7740 }, from: 40, to: 60 });
    c.updateSelected({ from: 38.2, to: 61.8, lines: '50, 100' });
    expect(vi.mocked(h.onChange).mock.calls.at(-1)![1]).toMatchObject({ from: 38.2, to: 61.8, lines: [50, 100] });
    c.updateSelected({ aPrice: 7679.75, bPrice: 7739.75 });
    expect(vi.mocked(h.onChange).mock.calls.at(-1)![1]).toMatchObject({ a: { time: 1010, price: 7679.75 }, b: { time: 1050, price: 7739.75 } });
    const h2 = host();
    const c2 = new RetraceToolController(h2);
    c2.setSymbol('ES');
    expect(vi.mocked(h2.onChange).mock.calls.at(-1)![0]).toHaveLength(1);
    c2.setSymbol('NQ');
    expect(vi.mocked(h2.onChange).mock.calls.at(-1)![0]).toHaveLength(0);
    c.removeSelected();
    expect(vi.mocked(h.onChange).mock.calls.at(-1)![0]).toHaveLength(0);
  });
});
