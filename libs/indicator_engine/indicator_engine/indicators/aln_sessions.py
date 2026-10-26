"""ALN sessions: Asia, London and New York ranges and the overnight pattern.

Times follow the nqstats ALN study, in New York time by default:

* Asia      20:00-02:00 (belongs to the next New York session)
* London    02:00-08:00
* New York  08:00-16:00

At the first New York bar the London range is compared with the Asia range:

* P1  London took both Asia's high and low
* P2  London stayed inside Asia's range
* P3  London took Asia's high only
* P4  London took Asia's low only

Outputs, per bar (NaN where they don't apply):

* ``asia_high/low``, ``london_high/low``, ``ny_high/low``: the running range of the
  session the bar belongs to, so a chart can draw a box that grows live.
* On New York bars: the final Asia and London ranges (``ref_*``), ``pattern`` (1-4),
  ``ny_open``, ``sdev_pts`` (1 Net Change SDEV in points for the 5-9 AM Pacific window,
  the same as the session SDEV indicator), ``up_at`` / ``dn_at`` (epoch ms of the first
  New York trade beyond London's high / low so far) and ``recent_1`` ... ``recent_8``,
  codes describing the previous New York sessions: ``pattern * 100 + reached * 10 +
  other_side_first`` where *reached* means the London level the pattern leans to was
  taken (P3: high, P4: low; for P1/P2 it is 0).
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
    MS_PER_DAY,
    MS_PER_MINUTE,
    _local_ms,
    _parse_clock,
    _warmup_bars,
    session_levels,
    to_epoch_ms,
)
from .session_sdev import (
    OUTPUTS as SDEV_OUTPUTS,
)

RECENT = 8
BOX_OUTPUTS = ["asia_high", "asia_low", "london_high", "london_low", "ny_high", "ny_low"]
NY_OUTPUTS = [
    "ref_asia_high",
    "ref_asia_low",
    "ref_london_high",
    "ref_london_low",
    "pattern",
    "ny_open",
    "sdev_pts",
    "up_at",
    "dn_at",
]
OUTPUTS = BOX_OUTPUTS + NY_OUTPUTS + [f"recent_{k}" for k in range(1, RECENT + 1)]
COL = {name: i for i, name in enumerate(OUTPUTS)}


def _pattern(ah: float, al: float, lh: float, ll: float) -> int:
    if lh > ah and ll < al:
        return 1
    if ah >= lh and al <= ll:
        return 2
    if lh > ah:
        return 3
    return 4


def aln_sessions(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    time_zone: str = "America/New_York",
    asia_start: str = "20:00",
    london_start: str = "02:00",
    ny_start: str = "08:00",
    ny_end: str = "16:00",
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)); see the module docstring."""
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    a0, l0, n0, n1 = (_parse_clock(v) for v in (asia_start, london_start, ny_start, ny_end))
    if not (l0 < n0 < n1 < a0):
        raise ValueError("Expected London start < New York start < New York end < Asia start")

    local = _local_ms(epoch_ms, ZoneInfo(time_zone))
    minute = (local % MS_PER_DAY) // MS_PER_MINUTE
    day = local // MS_PER_DAY
    tday = day + (minute >= a0)  # Asia belongs to the next New York session
    weekday = (tday + 3) % 7
    valid = np.isfinite(high) & np.isfinite(low) & (weekday < 5)
    sess = np.full(n, -1)
    sess[(minute >= a0) | (minute < l0)] = 0  # Asia
    sess[(minute >= l0) & (minute < n0)] = 1  # London
    sess[(minute >= n0) & (minute < n1)] = 2  # New York
    sess[~valid] = -1

    # 1 SDEV in points from the 5-9 AM Pacific window, as the session SDEV indicator draws it.
    sdev = session_levels(epoch_ms, open_, close, levels=(1.0,))
    sdev_pts = sdev[:, SDEV_OUTPUTS.index("+1")] - sdev[:, 0]

    history: list[int] = []  # codes of completed New York sessions, oldest first
    i = 0
    while i < n:
        if sess[i] < 0:
            i += 1
            continue
        d = tday[i]
        j = i
        while j < n and tday[j] == d:
            j += 1
        idx = np.arange(i, j)
        ranges: dict[int, tuple[float, float]] = {}
        for s, (hcol, lcol) in enumerate(
            (("asia_high", "asia_low"), ("london_high", "london_low"), ("ny_high", "ny_low"))
        ):
            rows = idx[sess[idx] == s]
            if rows.size == 0:
                continue
            run_h = np.maximum.accumulate(high[rows])
            run_l = np.minimum.accumulate(low[rows])
            out[rows, COL[hcol]] = run_h
            out[rows, COL[lcol]] = run_l
            ranges[s] = (float(run_h[-1]), float(run_l[-1]))
        ny_rows = idx[sess[idx] == 2]
        if ny_rows.size and 0 in ranges and 1 in ranges:
            (ah, al), (lh, ll) = ranges[0], ranges[1]
            p = _pattern(ah, al, lh, ll)
            up = np.where(high[ny_rows] > lh, epoch_ms[ny_rows], np.iinfo(np.int64).max)
            dn = np.where(low[ny_rows] < ll, epoch_ms[ny_rows], np.iinfo(np.int64).max)
            up_first = np.minimum.accumulate(up).astype(np.float64)
            dn_first = np.minimum.accumulate(dn).astype(np.float64)
            up_first[up_first >= np.iinfo(np.int64).max] = np.nan
            dn_first[dn_first >= np.iinfo(np.int64).max] = np.nan
            for name, value in (
                ("ref_asia_high", ah),
                ("ref_asia_low", al),
                ("ref_london_high", lh),
                ("ref_london_low", ll),
                ("pattern", p),
                ("ny_open", float(open_[ny_rows[0]])),
            ):
                out[ny_rows, COL[name]] = value
            out[ny_rows, COL["sdev_pts"]] = sdev_pts[ny_rows[0]]
            out[ny_rows, COL["up_at"]] = up_first
            out[ny_rows, COL["dn_at"]] = dn_first
            for k, code in enumerate(reversed(history[-RECENT:]), start=1):
                out[ny_rows, COL[f"recent_{k}"]] = code
            final_up, final_dn = up_first[-1], dn_first[-1]
            watch, other = (final_up, final_dn) if p == 3 else (final_dn, final_up)
            reached = p in (3, 4) and np.isfinite(watch)
            other_first = (
                p in (3, 4) and np.isfinite(other) and (not np.isfinite(watch) or other < watch)
            )
            history.append(p * 100 + int(reached) * 10 + int(other_first))
        i = j
    return out


class AlnSessions(IndicatorBase):
    """Asia / London / New York ranges with the overnight ALN pattern."""

    spec = IndicatorSpec(
        id="aln_sessions",
        name="ALN Sessions",
        description=(
            "Asia, London and New York session boxes, the overnight pattern (P1-P4) and "
            "what New York usually does next."
        ),
        parameters={
            "time_zone": {"type": "string", "default": "America/New_York"},
            "asia_start": {"type": "string", "default": "20:00"},
            "london_start": {"type": "string", "default": "02:00"},
            "ny_start": {"type": "string", "default": "08:00"},
            "ny_end": {"type": "string", "default": "16:00"},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        # Enough for 20 sessions of SDEV history and eight recent sessions.
        warmup_fn=lambda params: _warmup_bars({"lookback": 20}),
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        merged = {**defaults, **{k: v for k, v in params.items() if v is not None}}
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = aln_sessions(
                epoch_ms,
                data.data[:, a, idx["open"]],
                data.data[:, a, idx["high"]],
                data.data[:, a, idx["low"]],
                data.data[:, a, idx["close"]],
                time_zone=str(merged["time_zone"]),
                asia_start=str(merged["asia_start"]),
                london_start=str(merged["london_start"]),
                ny_start=str(merged["ny_start"]),
                ny_end=str(merged["ny_end"]),
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
