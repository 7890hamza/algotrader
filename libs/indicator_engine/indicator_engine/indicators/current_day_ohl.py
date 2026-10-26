"""Current day (session) open, high and low, like NinjaTrader's CurrentDayOHL.

Every bar gets the open of its session and the highest high / lowest low traded
in that session so far, so the high and low lines step outward as new extremes
print. Bars outside the session window get NaN.

The default session is the CME Globex day for equity index futures: it opens at
15:00 Pacific and runs to 14:00 Pacific the next day. Set ``session_start`` /
``session_end`` (for example 06:30 / 13:00) for the regular trading hours only.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import (
    MINUTES_PER_DAY,
    MS_PER_DAY,
    MS_PER_MINUTE,
    _local_ms,
    _parse_clock,
    to_epoch_ms,
)

OUTPUTS = ["open", "high", "low"]


def current_day_ohl(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    *,
    time_zone: str = "America/Los_Angeles",
    session_start: str = "15:00",
    session_end: str = "14:00",
) -> np.ndarray:
    """Return an array (time, 3): session open, running high, running low."""
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    start, end = _parse_clock(session_start), _parse_clock(session_end)
    local = _local_ms(np.asarray(epoch_ms, dtype=np.int64), ZoneInfo(time_zone))
    minute = (local % MS_PER_DAY) // MS_PER_MINUTE
    day = local // MS_PER_DAY
    if start < end:  # same-day session, e.g. 06:30-13:00
        inside = (minute >= start) & (minute < end)
        session = day
    else:  # overnight session, e.g. 15:00 -> 14:00 next day (equal times = 24 hours)
        inside = (minute >= start) | (minute < end) if start != end else np.ones(n, dtype=bool)
        session = day + (minute >= start)
    inside &= np.isfinite(open_) & np.isfinite(high) & np.isfinite(low)

    rows = np.flatnonzero(inside)
    if rows.size == 0:
        return out
    ids = session[rows]
    # A new session starts where the id changes (bars are in time order).
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    bounds = np.r_[starts, rows.size]
    for a, b in zip(bounds[:-1], bounds[1:]):
        r = rows[a:b]
        out[r, 0] = open_[r[0]]
        out[r, 1] = np.maximum.accumulate(high[r])
        out[r, 2] = np.minimum.accumulate(low[r])
    return out


class CurrentDayOHL(IndicatorBase):
    """Current session open, high and low."""

    spec = IndicatorSpec(
        id="current_day_ohl",
        name="Current Day OHL",
        description="The current day (session) open, high and low. Use on intraday charts.",
        parameters={
            "time_zone": {"type": "string", "default": "America/Los_Angeles"},
            "session_start": {"type": "string", "default": "15:00"},
            "session_end": {"type": "string", "default": "14:00"},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low"],
        supports_update=False,
        supports_vectorized=False,
        # One full session plus a weekend of 1-minute bars.
        warmup_fn=lambda params: 4 * MINUTES_PER_DAY,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        merged = {**defaults, **{k: v for k, v in params.items() if v is not None}}
        idx = {}
        for field in ("open", "high", "low"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = current_day_ohl(
                epoch_ms,
                data.data[:, a, idx["open"]],
                data.data[:, a, idx["high"]],
                data.data[:, a, idx["low"]],
                time_zone=str(merged["time_zone"]),
                session_start=str(merged["session_start"]),
                session_end=str(merged["session_end"]),
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
