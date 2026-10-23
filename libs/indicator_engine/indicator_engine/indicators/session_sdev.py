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
from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, Sequence

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
# Session start days (Monday == 0). CME's Globex day opens Sunday-Thursday afternoons.
SESSION_DAYS: dict[str, set[int]] = {"Mon-Fri": {0, 1, 2, 3, 4}, "Sun-Thu": {6, 0, 1, 2, 3}}
DEFAULT_LEVELS = "0.5, 1, 1.5"


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
    session_days: str = "Mon-Fri",
    extend: str = "session",
    levels: Sequence[float] = MULTIPLIERS,
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
    allowed_days = np.array(sorted(SESSION_DAYS[session_days]), dtype=np.int64)
    in_window = (
        valid & np.isin(weekday, allowed_days) & (minute >= start_m) & (minute < end_m)
    )
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

    # Each bar takes the levels of the latest session that opened at or before it,
    # either only inside that session's window or until the next session opens.
    session_of_bar = np.searchsorted(open_idx, np.arange(n), side="right") - 1
    has_session = session_of_bar >= 0
    if extend == "session":
        same_day = np.zeros(n, dtype=bool)
        same_day[has_session] = day[has_session] == days[session_of_bar[has_session]]
        has_session &= same_day & (minute >= start_m) & (minute < end_m)
    elif extend != "next_session":
        raise ValueError("extend must be 'session' or 'next_session'")
    rows = np.flatnonzero(has_session)
    k_for_rows = session_of_bar[rows]
    sig = sigma[k_for_rows]
    base = session_open[k_for_rows]
    drawable = np.isfinite(sig)
    rows, sig, base = rows[drawable], sig[drawable], base[drawable]

    out[rows, 0] = base
    shown = {round(float(m), 6) for m in levels}
    col = 1
    for m in MULTIPLIERS:
        if round(m, 6) in shown:
            out[rows, col] = base * (1 + m * sig / 100)
            out[rows, col + 1] = base * (1 - m * sig / 100)
        col += 2
    return out


def parse_levels(raw: str | Sequence[float]) -> tuple[float, ...]:
    """Parse "0.25, 0.5, 1" (or "all") into SDEV multipliers this indicator draws."""
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"", "all"}:
            return MULTIPLIERS
        values = [float(part) for part in text.replace(";", ",").split(",") if part.strip()]
    else:
        values = [float(v) for v in raw]
    unknown = [v for v in values if round(v, 6) not in {round(m, 6) for m in MULTIPLIERS}]
    if unknown:
        allowed = ", ".join(f"{m:g}" for m in MULTIPLIERS)
        raise ValueError(f"Unsupported SDEV levels {unknown}; choose from {allowed}")
    return tuple(values)


def _parameters(start: str, end: str, days: str) -> dict:
    return {
        "lookback": {"type": "int", "default": 20, "min": 2},
        "session_start": {"type": "string", "default": start},
        "session_end": {"type": "string", "default": end},
        "session_days": {"type": "string", "default": days, "options": list(SESSION_DAYS)},
        "time_zone": {"type": "string", "default": "America/Los_Angeles"},
        "levels": {"type": "string", "default": DEFAULT_LEVELS},
        "extend": {
            "type": "string",
            "default": "session",
            "options": ["session", "next_session"],
        },
    }


class SessionSDEV(IndicatorBase):
    """Net Change SDEV levels for the New York morning session (5-9 AM Pacific)."""

    spec = IndicatorSpec(
        id="session_sdev",
        name="Net Change SDEV",
        description=(
            "Session open and +/- SDEV levels from the net change of the previous "
            "complete sessions (population SDEV)."
        ),
        parameters=_parameters("05:00", "09:00", "Mon-Fri"),
        outputs=OUTPUTS,
        required_fields=["open", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=_warmup_bars,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        merged = {**defaults, **{k: v for k, v in params.items() if v is not None}}
        for field in ("open", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
        open_idx = int(np.where(data.fields == "open")[0][0])
        close_idx = int(np.where(data.fields == "close")[0][0])
        epoch_ms = to_epoch_ms(data.time)
        kwargs = dict(
            lookback=int(merged["lookback"]),
            session_start=str(merged["session_start"]),
            session_end=str(merged["session_end"]),
            time_zone=str(merged["time_zone"]),
            session_days=str(merged["session_days"]),
            extend=str(merged["extend"]),
            levels=parse_levels(merged["levels"]),
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


class CmeOpenSDEV(SessionSDEV):
    """The same Net Change SDEV recipe for the CME Globex open (3-7 PM Pacific)."""

    spec = replace(
        SessionSDEV.spec,
        id="cme_open_sdev",
        name="CME Open SDEV",
        description=(
            "CME Globex open (3 PM Pacific) and +/- SDEV levels from the net change of the "
            "previous complete 3-7 PM sessions (population SDEV)."
        ),
        parameters=_parameters("15:00", "19:00", "Sun-Thu"),
    )
