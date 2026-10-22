import { TickMarkType, type Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';

import {
  createChartTimeFormatters,
  DEFAULT_CHART_TIME_ZONE,
  displayTimeZoneForTimeframe,
} from '@/utils/chart/chartTimeZone';

// 2026-10-22 12:00:00 UTC = 05:00 Pacific Daylight Time.
const FIVE_AM_PDT = Date.UTC(2026, 9, 22, 12, 0, 0) / 1000;
// 2026-12-01 13:00:00 UTC = 05:00 Pacific Standard Time.
const FIVE_AM_PST = Date.UTC(2026, 11, 1, 13, 0, 0) / 1000;

describe('chartTimeZone', () => {
  it('defaults intraday labels to Pacific time', () => {
    expect(DEFAULT_CHART_TIME_ZONE).toBe('America/Los_Angeles');
    expect(displayTimeZoneForTimeframe('M1')).toBe('America/Los_Angeles');
    expect(displayTimeZoneForTimeframe('H4')).toBe('America/Los_Angeles');
  });

  it('keeps UTC labels for daily and longer candles', () => {
    expect(displayTimeZoneForTimeframe('D1')).toBe('UTC');
    expect(displayTimeZoneForTimeframe('W1')).toBe('UTC');
  });

  it('follows daylight saving time', () => {
    const { tickMarkFormatter } = createChartTimeFormatters('America/Los_Angeles');
    expect(tickMarkFormatter(FIVE_AM_PDT as Time, TickMarkType.Time)).toBe('05:00');
    expect(tickMarkFormatter(FIVE_AM_PST as Time, TickMarkType.Time)).toBe('05:00');
  });

  it('formats the crosshair label in the chosen zone', () => {
    const { timeFormatter } = createChartTimeFormatters('America/Los_Angeles');
    expect(timeFormatter(FIVE_AM_PDT as Time)).toBe("Thu 22 Oct '26 05:00");
  });

  it('formats date tick marks in the chosen zone', () => {
    const { tickMarkFormatter } = createChartTimeFormatters('America/Los_Angeles');
    // UTC midnight on Oct 23 is still Oct 22 in Pacific time.
    const utcMidnight = Date.UTC(2026, 9, 23) / 1000;
    expect(tickMarkFormatter(utcMidnight as Time, TickMarkType.DayOfMonth)).toBe('22');
    expect(tickMarkFormatter(utcMidnight as Time, TickMarkType.Month)).toBe('Oct');
  });

  it('shows daily candles without a clock in UTC', () => {
    const { timeFormatter } = createChartTimeFormatters('UTC');
    expect(timeFormatter((Date.UTC(2026, 9, 22) / 1000) as Time)).toBe("Thu 22 Oct '26");
  });
});
