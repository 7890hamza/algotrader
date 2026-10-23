import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IndicatorDataPoint, IndicatorInfo } from '@/types/contracts';
import { wsService } from '@/utils/websocketService';

import { IndicatorManager } from '@/utils/chart/IndicatorManager';

vi.mock('@/utils/websocketService', () => ({
  wsService: {
    send: vi.fn(),
  },
}));

const indicatorInfo: IndicatorInfo = {
  id: 1,
  indicator_id: 'sma',
  name: 'SMA',
  overlay: false,
  inputs: [],
  outputs: {
    timestamp: { type: 'time' },
    sma: {
      type: 'line',
      plotOptions: { color: '#fff', lineWidth: 2 },
    },
    signal: {
      type: 'histogram',
      plotOptions: { color: '#f00' },
    },
  },
  parameters: {},
};

const createChartManager = () => ({
  addSeries: vi.fn(),
  updateSeriesOptions: vi.fn(() => true),
  updateSeriesPoint: vi.fn(),
  removeSeries: vi.fn(),
  setSeriesData: vi.fn(() => true),
  getPaneHtmlElement: vi.fn(),
  series: new Map(),
});

describe('IndicatorManager', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(wsService.send).mockReset();
    vi.mocked(wsService.send).mockResolvedValue();
  });

  it('transforms indicator output data into finite numeric chart points', () => {
    const manager = new IndicatorManager(createChartManager());
    const data: IndicatorDataPoint[] = [
      { timestamp_ms: 1_000, sma: 1.2 },
      { timestamp_ms: 2_000, sma: null },
      { timestamp_ms: 3_000, sma: 'not-a-number' },
      { timestamp_ms: Number.NaN, sma: 1.5 },
    ];

    expect(manager.transformIndicatorData(data, 'sma')).toEqual([
      { time: 1, value: 1.2 },
    ]);
  });

  it('adds chart series for non-timestamp indicator outputs with default chart options', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(12345);
    const chartManager = createChartManager();
    const manager = new IndicatorManager(chartManager);
    const store = manager.indicatorsStore;
    const indicatorId = store.addIndicator(indicatorInfo, [
      { timestamp_ms: 1_000, sma: 1.2 },
    ], 1);

    await manager.addIndicatorSeries(indicatorId);

    expect(chartManager.addSeries).toHaveBeenCalledWith(
      `${indicatorId}_sma`,
      'line',
      [{ time: 1, value: 1.2 }],
      {
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        color: '#fff',
        lineWidth: 2,
      },
      1,
    );
    expect(chartManager.addSeries).toHaveBeenCalledTimes(1);
  });

  it('updates styles, refreshes series data, applies live points, and removes series with store data', () => {
    vi.spyOn(Date, 'now').mockReturnValue(12345);
    const chartManager = createChartManager();
    const manager = new IndicatorManager(chartManager);
    const store = manager.indicatorsStore;
    const indicatorId = store.addIndicator(indicatorInfo, [
      { timestamp_ms: 1_000, sma: 1.2, signal: null },
      { timestamp_ms: 2_000, sma: 1.3, signal: 2.1 },
    ], 1);
    chartManager.series.set(`${indicatorId}_sma`, {
      series: {
        setData: vi.fn(),
        update: vi.fn(),
        applyOptions: vi.fn(),
        barsInLogicalRange: vi.fn(),
      },
      type: 'line',
      data: [],
      options: {},
    });

    expect(manager.updateIndicatorStyles(indicatorId, 'sma', { color: '#0f0' })).toBe(true);
    manager.refreshIndicatorSeries(indicatorId);
    manager.updateIndicatorSeriesPoint(indicatorId, {
      timestamp_ms: 3_000,
      sma: 1.4,
      signal: 2.2,
    });
    manager.removeIndicatorSeriesAndData(indicatorId);

    expect(chartManager.updateSeriesOptions).toHaveBeenCalledWith(`${indicatorId}_sma`, {
      color: '#0f0',
    });
    expect(chartManager.setSeriesData).toHaveBeenCalledWith(`${indicatorId}_sma`, [
      { time: 1, value: 1.2 },
      { time: 2, value: 1.3 },
    ]);
    expect(chartManager.updateSeriesPoint).toHaveBeenCalledWith(`${indicatorId}_sma`, {
      time: 3,
      value: 1.4,
    });
    expect(chartManager.updateSeriesPoint).toHaveBeenCalledWith(`${indicatorId}_signal`, {
      time: 3,
      value: 2.2,
    });
    expect(chartManager.removeSeries).toHaveBeenCalledWith(`${indicatorId}_sma`);
    expect(chartManager.removeSeries).toHaveBeenCalledWith(`${indicatorId}_signal`);
    expect(store.exists(indicatorId)).toBe(false);
  });
});

describe('IndicatorManager session levels', () => {
  const levelInfo: IndicatorInfo = {
    id: 6,
    indicator_id: 'session_sdev',
    name: 'Net Change SDEV',
    overlay: true,
    inputs: [],
    outputs: {
      open: { type: 'level', label: 'Open', plotOptions: { color: '#E8B04F', lineWidth: 2 } },
      '+1': { type: 'level', label: '+1', touch: 'high', plotOptions: { color: '#26A69A' } },
    },
    parameters: {},
  };

  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('draws level outputs as session levels instead of line series', async () => {
    const chartManager = {
      ...createChartManager(),
      setSessionLevels: vi.fn(() => true),
      clearSessionLevels: vi.fn(() => true),
    };
    const manager = new IndicatorManager(chartManager);
    const id = manager.indicatorsStore.addIndicator(levelInfo, [
      { timestamp_ms: 60_000, open: 100, '+1': 101 },
      { timestamp_ms: 120_000, open: 100, '+1': 101 },
    ], 0);

    await manager.addIndicatorSeries(id);

    expect(chartManager.addSeries).not.toHaveBeenCalled();
    const [ownerId, seriesKey, segments] = chartManager.setSessionLevels.mock.calls[0] as unknown as [
      string,
      string,
      { label: string; endTime: number }[],
    ];
    expect(ownerId).toBe(id);
    expect(seriesKey).toBe('ohlc');
    expect(segments.map((s) => s.label).sort()).toEqual(['+1', 'Open']);

    manager.updateIndicatorSeriesPoint(id, { timestamp_ms: 180_000, open: 100, '+1': 101 });
    const lastCall = chartManager.setSessionLevels.mock.calls.at(-1) as unknown as [
      string,
      string,
      { endTime: number }[],
    ];
    expect(lastCall[2][0].endTime).toBe(180);

    manager.updateIndicatorStyles(id, 'open', { color: '#ffffff' });
    const styled = chartManager.setSessionLevels.mock.calls.at(-1) as unknown as [
      string,
      string,
      { label: string; color: string }[],
    ];
    expect(styled[2].find((s) => s.label === 'Open')?.color).toBe('#ffffff');

    manager.removeIndicatorSeries(id);
    expect(chartManager.clearSessionLevels).toHaveBeenCalledWith(id);
  });
});
