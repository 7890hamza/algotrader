"""Candle timeframes for SEIZ: 15m to 1W, all on the CME clock (New York time).

* 15m / 30m: clock-aligned.
* 1h ... 12h: blocks of N hours counted from the 6 PM ET Globex open; the last block of a
  trading day stops at the 5 PM close (so 5h, 7h ... have a short last candle, like on a chart
  whose session template starts at 6 PM).
* 1D: the CME trading day (6 PM to 5 PM). 1W: Sunday 6 PM to Friday 5 PM.
"""

from __future__ import annotations

import numpy as np

MS_MIN = 60_000
MS_HOUR = 3_600_000
MS_DAY = 86_400_000
CME_OPEN = 18 * 60       # minutes after local midnight
CME_CLOSE = 17 * 60

TIMEFRAMES = ["15m", "30m", "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h", "1d", "1w"]
LABELS = {tf: tf.upper() if tf in ("1d", "1w") else tf for tf in TIMEFRAMES}


def hours_of(tf: str) -> int | None:
    return int(tf[:-1]) if tf.endswith("h") else None


def frame_keys(local_ms: np.ndarray, tf: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each bar (local New York epoch ms): candle key, candle start and nominal end (local ms)."""
    local_ms = np.asarray(local_ms, dtype=np.int64)
    day = local_ms // MS_DAY
    minute = (local_ms // MS_MIN) % 1440
    cme_day = day + (minute >= CME_OPEN)                    # trading day the bar belongs to
    day_start = (cme_day - 1) * MS_DAY + CME_OPEN * MS_MIN  # 6 PM the evening before
    day_end = cme_day * MS_DAY + CME_CLOSE * MS_MIN         # 5 PM
    if tf in ("15m", "30m"):
        size = (15 if tf == "15m" else 30) * MS_MIN
        key = local_ms // size
        start = key * size
        return key, start, start + size
    n = hours_of(tf)
    if n is not None:
        idx = (local_ms - day_start) // (n * MS_HOUR)
        start = day_start + idx * n * MS_HOUR
        return cme_day * 64 + idx, start, np.minimum(start + n * MS_HOUR, day_end)
    if tf == "1d":
        return cme_day, day_start, day_end
    if tf == "1w":
        week = (cme_day + 3) // 7                           # Monday-based weeks
        monday = week * 7 - 3                               # cme_day number of that Monday
        return week, (monday - 1) * MS_DAY + CME_OPEN * MS_MIN, (monday + 4) * MS_DAY + CME_CLOSE * MS_MIN
    raise ValueError(f"unknown timeframe {tf}")


def in_session(local_ms: np.ndarray) -> np.ndarray:
    minute = (np.asarray(local_ms, dtype=np.int64) // MS_MIN) % 1440
    return ~((minute >= CME_CLOSE) & (minute < CME_OPEN))
