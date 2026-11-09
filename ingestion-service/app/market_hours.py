"""CME equity-futures trading hours, so stray bars from a closed market are never stored.

Some MT5 feeds keep sending a flat "last price" bar now and then while the exchange is
closed (weekends and the daily 4-5 PM Central break). Those bars are not trades; they
show up as lone candles in the middle of the weekend gap.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
DEFAULT_SYMBOLS = "ES,MES,NQ,MNQ,YM,MYM,RTY,M2K"


def cme_symbols() -> frozenset[str]:
    raw = os.environ.get("CME_SESSION_SYMBOLS", DEFAULT_SYMBOLS)
    return frozenset(s.strip().upper() for s in raw.split(",") if s.strip())


def cme_closed(timestamp_ms: int) -> bool:
    """True when the minute starting at `timestamp_ms` is outside CME Globex hours.

    Globex runs Sunday 5 PM to Friday 4 PM Central, with a break from 4 to 5 PM
    Central Monday through Thursday.
    """
    t = datetime.fromtimestamp(timestamp_ms / 1000, tz=CHICAGO)
    wd, h = t.weekday(), t.hour  # Monday = 0
    if wd == 5:  # Saturday
        return True
    if wd == 6:  # Sunday: opens at 5 PM
        return h < 17
    if wd == 4:  # Friday: closes at 4 PM
        return h >= 16
    return h == 16  # daily break


def drop_closed_bars(
    symbol: str, candles: list[dict], symbols: frozenset[str] | None = None
) -> list[dict]:
    """Remove bars stamped while the market was closed (only for CME session symbols)."""
    if symbol.upper() not in (symbols if symbols is not None else cme_symbols()):
        return candles
    return [c for c in candles if not cme_closed(int(c["timestamp_ms"]))]


def open_minutes_between(
    symbol: str, after_ms: int, before_ms: int, symbols: frozenset[str] | None = None
) -> int:
    """How many trading minutes lie strictly between two bar times (capped at 3 days of
    minutes). Symbols without known session hours return 0: their gaps can be real."""
    first, last = after_ms + 60_000, before_ms - 60_000
    if last < first:
        return 0
    span = min((last - first) // 60_000 + 1, 3 * 1440)
    if symbol.upper() not in (symbols if symbols is not None else cme_symbols()):
        return 0
    return sum(1 for k in range(int(span)) if not cme_closed(first + k * 60_000))
