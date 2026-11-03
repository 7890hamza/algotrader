import { describe, expect, it } from 'vitest';

import { resolveContractSpec, rootSymbol } from '@/utils/chart/contractSpecs';
import { buildPositionModel, createPosition, flipSide, moveHandle } from '@/utils/chart/positionTool';

describe('contract specs', () => {
  it('knows futures by root, month code or broker spelling', () => {
    expect(rootSymbol('ESZ6')).toBe('ES');
    expect(rootSymbol('@ENQ')).toBe('NQ');
    expect(rootSymbol('/MES')).toBe('MES');
    expect(resolveContractSpec({ symbol: 'ES', minMove: 0.25 })).toMatchObject({ tickSize: 0.25, tickValue: 12.5, source: 'table' });
  });

  it('prefers MT5, then a custom value, and guesses for unknown symbols', () => {
    const mt5 = resolveContractSpec({ symbol: 'ES', minMove: 0.25, broker: { tick_size: 0.25, tick_value: 12.5, currency: 'USD' } });
    expect(mt5.source).toBe('mt5');
    const custom = resolveContractSpec({ symbol: 'ES', minMove: 0.25, customPointValue: 5 });
    expect(custom).toMatchObject({ tickValue: 1.25, source: 'custom' });
    expect(resolveContractSpec({ symbol: 'FOO', minMove: 0.01 })).toMatchObject({ tickSize: 0.01, source: 'guess' });
  });
});

describe('position tool', () => {
  const nq = resolveContractSpec({ symbol: 'NQ', minMove: 0.25 });

  it('matches the photo: NQ short 29004.75, stop 29025.50, target 28901', () => {
    const m = buildPositionModel({ side: 'short', time: 0, entry: 29004.75, stop: 29025.5, target: 28901, qty: 1 }, nq);
    expect(m.valid).toBe(true);
    expect(m.risk).toEqual({ points: 20.75, ticks: 83, money: 415 });
    expect(m.reward.money).toBe(2075);
    expect(m.rr).toBeCloseTo(5, 5);
    expect(m.lines.filter((l) => l.key === 'ladder').map((l) => l.label.split(' ')[0])).toEqual(['0.5R', '1R', '2R', '3R', '4R']);
  });

  it('places the stop past the recent swing and the target at 2R', () => {
    const s = createPosition('long', 100.1, 1, [{ high: 101, low: 98 }, { high: 102, low: 99 }], 0.25);
    expect(s).toMatchObject({ entry: 100, stop: 97.75, target: 104.5 });
  });

  it('drags and flips with tick snapping', () => {
    const s = createPosition('long', 100, 1, [], 0.25);
    expect(moveHandle(s, 'stop', 98.13, 0.25).stop).toBe(98.25);
    const f = flipSide(s, 0.25);
    expect(f.side).toBe('short');
    expect(f.stop).toBeGreaterThan(f.entry);
    expect(buildPositionModel({ ...s, stop: 101 }, nq).valid).toBe(false);
  });
});
