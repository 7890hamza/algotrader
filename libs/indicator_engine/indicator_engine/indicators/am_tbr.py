"""AM TBR (nqstats.com/am_tbr) with its MAE / MFE zones, measured on ES.

TBR = 08:00-12:00 New York (05:00-09:00 Pacific). TBR Open = the 08:00 open.
1 SDEV = sample SDEV (ddof=1) of the previous 20 sessions' % net change, in points
``open * SDEV / 100``. Lines at TBR Open +/- 0.25 SDEV.

After the first touch of either line three zones appear, in SDEV units from TBR Open,
from the ES 2016-2025 study (1-minute AMP data), for the hour of the touch:

* stretch  - how far price pushed past the touched line on days it came back to
             TBR Open (median to 90th percentile; ``*_mid`` = 75th percentile)
* runaway  - how far it ran by 12:00 on days it never came back
* follow   - how far it kept going past TBR Open, on the other side, after coming back

Other outputs: ``touch_side`` (+1 / -1), ``touch_at`` and ``revert_at`` (epoch ms of the
first touch and of the first trade back at TBR Open after it).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.tensor import Tensor
from .session_sdev import (
    MS_PER_DAY,
    MS_PER_MINUTE,
    SessionSDEV,
    _local_ms,
    _parameters,
    session_levels,
    to_epoch_ms,
)
from .session_sdev import (
    OUTPUTS as SDEV_OUTPUTS,
)

ZONES = ("stretch", "runaway", "follow")
OUTPUTS = ["open", "+0.25", "-0.25", "touch_side", "touch_at", "revert_at"] + [
    f"{z}_{e}" for z in ZONES for e in ("near", "far", "mid")
]
COL = {name: i for i, name in enumerate(OUTPUTS)}

# (median, p75, p90) in SDEV, by touched side and New York hour of the touch.
# ES 2016-2025; touches from 10:00 on use the 09:00 row (only ~20 such days per side).
ZONE_STATS: dict[tuple[int, int], dict[str, tuple[float, float, float]]] = {
    (1, 8): {
        "stretch": (0.425, 0.649, 0.981),
        "runaway": (1.511, 2.013, 2.380),
        "follow": (0.643, 1.141, 1.952),
    },
    (1, 9): {
        "stretch": (0.372, 0.496, 0.633),
        "runaway": (0.969, 1.261, 1.545),
        "follow": (0.372, 0.796, 1.413),
    },
    (-1, 8): {
        "stretch": (0.438, 0.643, 0.975),
        "runaway": (1.586, 2.598, 3.091),
        "follow": (0.588, 1.165, 1.793),
    },
    (-1, 9): {
        "stretch": (0.379, 0.525, 0.716),
        "runaway": (1.123, 1.403, 1.847),
        "follow": (0.331, 0.605, 1.056),
    },
}
NEW_YORK = ZoneInfo("America/New_York")
SESSION_GAP_MS = 2 * 60 * MS_PER_MINUTE


def am_tbr(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    **level_kwargs,
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)); see the module docstring."""
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    lv = session_levels(epoch_ms, open_, close, levels=(0.25,), **level_kwargs)
    base, up, dn = lv[:, 0], lv[:, SDEV_OUTPUTS.index("+0.25")], lv[:, SDEV_OUTPUTS.index("-0.25")]
    out[:, COL["open"]], out[:, COL["+0.25"]], out[:, COL["-0.25"]] = base, up, dn
    ny_hour = (_local_ms(epoch_ms, NEW_YORK) % MS_PER_DAY) // (60 * MS_PER_MINUTE)

    rows = np.flatnonzero(np.isfinite(base) & np.isfinite(up))
    if rows.size == 0:
        return out
    new = np.r_[
        True, (base[rows[1:]] != base[rows[:-1]]) | (np.diff(epoch_ms[rows]) > SESSION_GAP_MS)
    ]
    bounds = np.r_[np.flatnonzero(new), rows.size]
    for a, b in zip(bounds[:-1], bounds[1:]):
        r = rows[a:b]
        o, u, d = base[r[0]], up[r[0]], dn[r[0]]
        pts = (u - o) / 0.25
        hits = np.flatnonzero((high[r] >= u) | (low[r] <= d))
        if hits.size == 0:
            continue
        k = hits[0]
        both = high[r[k]] >= u and low[r[k]] <= d
        side = (
            1
            if high[r[k]] >= u and (not both or abs(open_[r[k]] - u) <= abs(open_[r[k]] - d))
            else -1
        )
        after = r[k:]
        out[after, COL["touch_side"]] = side
        out[after, COL["touch_at"]] = epoch_ms[r[k]]
        back = (low[r[k + 1 :]] <= o) if side == 1 else (high[r[k + 1 :]] >= o)
        if back.any():
            j = k + 1 + int(np.argmax(back))
            out[r[j:], COL["revert_at"]] = epoch_ms[r[j]]
        stats = ZONE_STATS[(side, min(max(int(ny_hour[r[k]]), 8), 9))]
        for zone, (med, p75, p90) in stats.items():
            direction = -side if zone == "follow" else side
            out[after, COL[f"{zone}_near"]] = o + direction * med * pts
            out[after, COL[f"{zone}_far"]] = o + direction * p90 * pts
            out[after, COL[f"{zone}_mid"]] = o + direction * p75 * pts
    return out


class AmTBR(SessionSDEV):
    """AM Time-Based Range: TBR Open, +/- 0.25 SDEV and the MAE / MFE zones."""

    spec = replace(
        SessionSDEV.spec,
        id="am_tbr",
        name="AM TBR",
        description=(
            "AM Time-Based Range (8:00-12:00 New York): TBR Open, +/- 0.25 SDEV (sample "
            "SDEV of 20 sessions) and, after the first touch, the usual stretch, runaway "
            "and follow-through zones from ES 2016-2025."
        ),
        parameters={
            **{k: v for k, v in _parameters("05:00", "09:00", "Mon-Fri").items() if k != "levels"},
            "ddof": {"type": "int", "default": 1, "min": 0, "max": 1},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
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
            out[:, a, :] = am_tbr(
                epoch_ms,
                *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")),
                lookback=int(merged["lookback"]),
                session_start=str(merged["session_start"]),
                session_end=str(merged["session_end"]),
                time_zone=str(merged["time_zone"]),
                session_days=str(merged["session_days"]),
                extend=str(merged["extend"]),
                ddof=int(merged["ddof"]),
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
