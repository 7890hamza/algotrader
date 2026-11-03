import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PositionToolController, type PositionToolHost } from '@/utils/chart/positionToolController';

function host(overrides: Partial<PositionToolHost> = {}): PositionToolHost {
  return {
    getSeries: () => null,
    coordinateToPrice: (y) => 5000 - y / 4,
    coordinateToTime: () => 1_700_000_000,
    recentBars: () => [{ high: 5010, low: 4990 }],
    setDragScroll: vi.fn(),
    onChange: vi.fn(),
    onPlaced: vi.fn(),
    ...overrides,
  };
}

describe('PositionToolController', () => {
  beforeEach(() => localStorage.clear());

  it('places a plan on click in long mode, keeps it per symbol, and swallows the click', () => {
    const h = host();
    const c = new PositionToolController(h);
    const pane = document.createElement('div');
    const below = vi.fn();
    pane.appendChild(document.createElement('canvas')).addEventListener('pointerdown', below);
    c.setPane(pane);
    c.setMarket('ES', 0.25);
    c.setPlacing('long');
    pane.querySelector('canvas')!.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 10, clientY: 40 }));
    expect(below).not.toHaveBeenCalled();
    expect(h.onPlaced).toHaveBeenCalled();
    const [state, model] = vi.mocked(h.onChange).mock.calls.at(-1)!;
    // Entry at the click (y 40 = 4990); the swing low is not below it, so the stop is 16 ticks away.
    expect(state).toMatchObject({ side: 'long', entry: 4990, stop: 4986, target: 4998, qty: 1 });
    expect(model?.valid).toBe(true);
    const h2 = host();
    const c2 = new PositionToolController(h2);
    c2.setMarket('ES', 0.25);
    expect(vi.mocked(h2.onChange).mock.calls.at(-1)![0]).toMatchObject({ side: 'long', entry: 4990 });
    c2.setMarket('NQ', 0.25);
    expect(vi.mocked(h2.onChange).mock.calls.at(-1)![0]).toBeNull();
  });
});
