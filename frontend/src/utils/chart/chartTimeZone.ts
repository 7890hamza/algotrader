import { TickMarkType, type Time } from 'lightweight-charts';

import { timeframeToMinutes } from '@/utils/timeframes';

/**
 * Wall-clock time zone for intraday chart labels. Candle timestamps stay UTC
 * everywhere; only the labels drawn on the time axis and crosshair change.
 * Override with VITE_CHART_TIME_ZONE (an IANA name such as "America/New_York").
 */
export const DEFAULT_CHART_TIME_ZONE =
  (import.meta.env.VITE_CHART_TIME_ZONE as string | undefined)?.trim() || 'America/Los_Angeles';

const MINUTES_PER_DAY = 1440;

/**
 * Daily and longer Candles are stamped at UTC midnight. Shown in a zone west of
 * UTC they would read as the previous evening, so they keep UTC labels.
 */
export function displayTimeZoneForTimeframe(
  timeframe: string,
  intradayTimeZone: string = DEFAULT_CHART_TIME_ZONE,
): string {
  let minutes: number;
  try {
    minutes = timeframeToMinutes(timeframe);
  } catch {
    return intradayTimeZone;
  }
  return minutes >= MINUTES_PER_DAY ? 'UTC' : intradayTimeZone;
}

type Parts = Record<'year' | 'month' | 'day' | 'weekday' | 'hour' | 'minute' | 'second', string>;

function partsFormatter(timeZone: string): (epochSeconds: number) => Parts {
  const format = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  return (epochSeconds: number) => {
    const parts = {} as Parts;
    for (const part of format.formatToParts(new Date(epochSeconds * 1000))) {
      if (part.type in { year: 1, month: 1, day: 1, weekday: 1, hour: 1, minute: 1, second: 1 }) {
        parts[part.type as keyof Parts] = part.value;
      }
    }
    return parts;
  };
}

function toEpochSeconds(time: Time): number | null {
  return typeof time === 'number' && Number.isFinite(time) ? time : null;
}

export interface ChartTimeFormatters {
  /** Crosshair label, e.g. "Thu 22 Oct '26 05:00". */
  timeFormatter: (time: Time) => string;
  /** Time-axis labels. */
  tickMarkFormatter: (time: Time, tickMarkType: TickMarkType) => string;
}

export function createChartTimeFormatters(timeZone: string): ChartTimeFormatters {
  const partsOf = partsFormatter(timeZone);
  const showsClock = timeZone !== 'UTC';

  return {
    timeFormatter(time: Time): string {
      const seconds = toEpochSeconds(time);
      if (seconds === null) return '';
      const p = partsOf(seconds);
      const date = `${p.weekday} ${p.day} ${p.month} '${p.year.slice(-2)}`;
      return showsClock || seconds % 86_400 !== 0 ? `${date} ${p.hour}:${p.minute}` : date;
    },

    tickMarkFormatter(time: Time, tickMarkType: TickMarkType): string {
      const seconds = toEpochSeconds(time);
      if (seconds === null) return '';
      const p = partsOf(seconds);
      switch (tickMarkType) {
        case TickMarkType.Year:
          return p.year;
        case TickMarkType.Month:
          return p.month;
        case TickMarkType.DayOfMonth:
          return p.day;
        case TickMarkType.TimeWithSeconds:
          return `${p.hour}:${p.minute}:${p.second}`;
        case TickMarkType.Time:
        default:
          return `${p.hour}:${p.minute}`;
      }
    },
  };
}
