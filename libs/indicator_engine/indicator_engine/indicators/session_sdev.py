"""Net Change SDEV levels for a fixed intraday session.

For every weekday the session (default 5:00-9:00 AM Pacific) has:

* open  = open of the first bar that starts in the first 5 minutes of the session
* close = close of the last bar that starts in the last 5 minutes of the session
* net change % = (close - open) / open * 100

A session is complete when it has both ends and covers at least 200 of every 240
minutes (5/6 of the window). One SDEV for a session is the population standard
deviation (ddof=0) of the net change % of the ``lookback`` complete sessions before
it, and its levels are ``open * (1 +/- m * SDEV / 100)``. Levels are frozen at the
session open and drawn from that bar until the next session opens, so nothing from
the session itself or later leaks in.

For bars longer than 5 minutes the open/close windows widen to one bar.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase

MULTIPLIERS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
OUTPUTS = ["open"] + [f"{sign}{m:g}" for m in MULTIPLIERS for sign in ("+", "-")]

MS_PER_MINUTE = 60_000
MS_PER_HOUR = 3_600_000
MS_PER_DAY = 86_400_000
MINUTES_PER_DAY = 1440
EDGE_MINUTES = 5
COVERAGE = 200 / 240


def _parse_clock(value: str) -> int:
    hours, _, minutes = str(value).strip().partition(":")
    result = int(hours) * 60 + int(minutes or 0)
    if not 0 <= result < MINUTES_PER_DAY:
        raise ValueError(f"Invalid clock time: {value!r}")
    return result


def _warmup_bars(params: Dict) -> int:
    """Bars of 1-minute history that hold ``lookback`` sessions plus slack for
    weekends and holidays. Larger bars simply load more calendar time."""
    lookback = int(params.get("lookback", 20))
    calendar_days = math.ceil((lookback + 5) * 7 / 5)
    return calendar_days * MINUTES_PER_DAY


def to_epoch_ms(times: np.ndarray) -> np.ndarray:
    """Epoch milliseconds from int ms, datetime64 or Timestamp/datetime objects."""
    arr = np.asarray(times)
    if arr.size == 0:
        return np.empty(0, dtype=np.int64)
    if np.issubdtype(arr.dtype, np.integer):
        return arr.astype(np.int64)
    if np.issubdtype(arr.dtype, np.datetime64):
        return arr.astype("datetime64[ms]").astype(np.int64)
    import pandas as pd

    index = pd.DatetimeIndex(pd.to_datetime(arr, utc=True)).as_unit("ms")
    return index.asi8.astype(np.int64)


def _utc_offset_ms(epoch_hour: int, zone: ZoneInfo) -> int:
    offset = datetime.fromtimestamp(epoch_hour * 3600, tz=timezone.utc).astimezone(zone).utcoffset()
    return int(offset.total_seconds() * 1000) if offset is not None else 0


def _local_ms(epoch_ms: np.ndarray, zone: ZoneInfo) -> np.ndarray:
    hours, inverse = np.unique(epoch_ms // MS_PER_HOUR, return_inverse=True)
    offsets = np.array([_utc_offset_ms(int(h), zone) for h in hours], dtype=np.int64)
    return epoch_ms + offsets[inverse]


def session_levels(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    *,
    lookback: int = 20,
    session_start: str = "05:00",
    session_end: str = "09:00",
    time_zone: str = "America/Los_Angeles",
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)) of open and +/- SDEV levels per bar."""
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out

    start_m, end_m = _parse_clock(session_start), _parse_clock(session_end)
    if end_m <= start_m:
        raise ValueError("session_end must be after session_start on the same day")

    local = _local_ms(epoch_ms, ZoneInfo(time_zone))
    day = local // MS_PER_DAY
    minute = (local % MS_PER_DAY) // MS_PER_MINUTE
    weekday = (day + 3) % 7  # 1970-01-01 was a Thursday; Monday == 0

    diffs = np.diff(epoch_ms)
    bar_minutes = max(1, int(np.median(diffs) // MS_PER_MINUTE)) if diffs.size else 1
    edge = max(EDGE_MINUTES, bar_minutes)
    min_bars = math.ceil((end_m - start_m) * COVERAGE / bar_minutes)

    valid = np.isfinite(open_) & np.isfinite(close)
    in_window = valid & (weekday < 5) & (minute >= start_m) & (minute < end_m)
    open_mask = in_window & (minute < start_m + edge)
    close_mask = in_window & (minute >= end_m - edge)

    days, first_open = np.unique(day[open_mask], return_index=True)
    open_idx = np.flatnonzero(open_mask)[first_open]
    if days.size == 0:
        return out

    close_positions = np.flatnonzero(close_mask)
    close_days_rev, last_rev = np.unique(day[close_positions][::-1], return_index=True)
    close_idx_by_day = dict(zip(close_days_rev.tolist(), close_positions[::-1][last_rev].tolist()))
    win_days, win_counts = np.unique(day[in_window], return_counts=True)
    counts_by_day = dict(zip(win_days.tolist(), win_counts.tolist()))

    session_open = open_[open_idx]
    net_pct = np.full(days.size, np.nan)
    complete = np.zeros(days.size, dtype=bool)
    for k, d in enumerate(days.tolist()):
        c_idx = close_idx_by_day.get(d)
        if c_idx is None or c_idx < open_idx[k] or counts_by_day.get(d, 0) < min_bars:
            continue
        net_pct[k] = (close[c_idx] - session_open[k]) / session_open[k] * 100
        complete[k] = True

    sigma = np.full(days.size, np.nan)
    complete_pos = np.flatnonzero(complete)
    for k in range(days.size):
        before = complete_pos[complete_pos < k]
        if before.size >= lookback:
            sigma[k] = float(np.std(net_pct[before[-lookback:]], ddof=0))

    # Each bar takes the levels of the latest session that opened at or before it.
    session_of_bar = np.searchsorted(open_idx, np.arange(n), side="right") - 1
    has_session = session_of_bar >= 0
    rows = np.flatnonzero(has_session)
    k_for_rows = session_of_bar[rows]
    sig = sigma[k_for_rows]
    base = session_open[k_for_rows]
    drawable = np.isfinite(sig)
    rows, sig, base = rows[drawable], sig[drawable], base[drawable]

    out[rows, 0] = base
    col = 1
    for m in MULTIPLIERS:
        out[rows, col] = base * (1 + m * sig / 100)
        out[rows, col + 1] = base * (1 - m * sig / 100)
        col += 2
    return out


class SessionSDEV(IndicatorBase):
    """Net Change SDEV levels for a fixed intraday session."""

    spec = IndicatorSpec(
        id="session_sdev",
        name="Net Change SDEV",
        description=(
            "Session open and +/- SDEV levels from the net change of the previous "
            "complete sessions (population SDEV)."
        ),
        parameters={
            "lookback": {"type": "int", "default": 20, "min": 2},
            "session_start": {"type": "string", "default": "05:00"},
            "session_end": {"type": "string", "default": "09:00"},
            "time_zone": {"type": "string", "default": "America/Los_Angeles"},
        },
        outputs=OUTPUTS,
        required_fields=["open", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=_warmup_bars,
        requires_full_warmup=False,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        for field in ("open", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
        open_idx = int(np.where(data.fields == "open")[0][0])
        close_idx = int(np.where(data.fields == "close")[0][0])
        epoch_ms = to_epoch_ms(data.time)
        kwargs = dict(
            lookback=int(params.get("lookback", 20)),
            session_start=str(params.get("session_start", "05:00")),
            session_end=str(params.get("session_end", "09:00")),
            time_zone=str(params.get("time_zone", "America/Los_Angeles")),
        )
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = session_levels(
                epoch_ms,
                data.data[:, a, open_idx],
                data.data[:, a, close_idx],
                **kwargs,  # type: ignore[arg-type]
            )
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={
                "time": data.time,
                "asset": data.assets,
                "output": np.array(OUTPUTS, dtype=object),
            },
        )
