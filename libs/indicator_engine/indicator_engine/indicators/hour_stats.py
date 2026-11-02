"""Hour Stats (nqstats.com/hour_stats) measured on ES, 08:00-16:00 New York.

For each hour from 08:00 to 15:00 New York: the hour open and the prior hour's high
and low. A setup needs the hour open strictly inside the prior hour's range. A breach is
a trade at least 1 tick beyond the prior high or low (first breach only); price is "back"
when a later candle trades to the hour open before the hour ends.

Outputs (on every candle of the hour): ``open``, ``ph`` and ``pl`` (prior hour high /
low) and ``setup`` (1 when the open was inside the prior range, else 0). From the breach
on: ``side`` (+1 prior high / -1 prior low), ``breach_at`` (epoch ms), ``seg`` (0 / 1 / 2
for a breach in minutes 0-19 / 20-39 / 40-59) and two zones from the ES 2016-2025 study
for that hour (median to 90th percentile, ``*_mid`` the 75th):

* ``stretch`` (MAE) - how far past the breached level price went on hours that came back
* ``follow`` (MFE) - how far past the open, on the other side, price went after coming back

``revert_at`` is the epoch ms of the first trade back at the open, from that candle on.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import MS_PER_MINUTE, _local_ms, to_epoch_ms

MS_PER_HOUR = 60 * MS_PER_MINUTE
NEW_YORK = ZoneInfo("America/New_York")
TICK = 0.25
FIRST_HOUR, LAST_HOUR = 8, 15
ZONES = ("stretch", "follow")
OUTPUTS = ["open", "ph", "pl", "setup", "side", "breach_at", "seg", "revert_at"] + [
    f"{z}_{e}" for z in ZONES for e in ("near", "far", "mid")
]
COL = {name: i for i, name in enumerate(OUTPUTS)}

# (median, p75, p90) in % of the hour open, by New York hour. ES 2016-2025, AMP 1-minute.
ZONE_STATS: dict[int, dict[str, tuple[float, float, float]]] = {
    8: {"stretch": (0.0250, 0.0560, 0.1063), "follow": (0.0798, 0.1622, 0.3343)},
    9: {"stretch": (0.0370, 0.0877, 0.1618), "follow": (0.1275, 0.2596, 0.4265)},
    10: {"stretch": (0.0464, 0.1005, 0.1886), "follow": (0.1199, 0.2517, 0.4477)},
    11: {"stretch": (0.0359, 0.0766, 0.1419), "follow": (0.0984, 0.1881, 0.3488)},
    12: {"stretch": (0.0319, 0.0664, 0.1367), "follow": (0.0826, 0.1790, 0.3028)},
    13: {"stretch": (0.0323, 0.0715, 0.1316), "follow": (0.0810, 0.1733, 0.3224)},
    14: {"stretch": (0.0381, 0.0802, 0.1671), "follow": (0.0913, 0.1922, 0.3635)},
    15: {"stretch": (0.0376, 0.0878, 0.1680), "follow": (0.1172, 0.2458, 0.4422)},
}


def hour_stats(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    tick: float = TICK,
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)); see the module docstring."""
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    local = _local_ms(epoch_ms, NEW_YORK)
    hour_key = local // MS_PER_HOUR
    hour_of_day = (local // MS_PER_HOUR) % 24
    minute = (local // MS_PER_MINUTE) % 60
    starts = np.flatnonzero(np.r_[True, hour_key[1:] != hour_key[:-1]])
    ends = np.r_[starts[1:], n]
    for g, (a, b) in enumerate(zip(starts, ends)):
        hod = int(hour_of_day[a])
        if not (FIRST_HOUR <= hod <= LAST_HOUR) or g == 0:
            continue
        pa, pb = starts[g - 1], ends[g - 1]
        if hour_key[pa] != hour_key[a] - 1:
            continue  # no prior hour (session break)
        rows = np.arange(a, b)
        ph, pl = float(np.nanmax(high[pa:pb])), float(np.nanmin(low[pa:pb]))
        o = float(open_[a])
        out[rows, COL["open"]], out[rows, COL["ph"]], out[rows, COL["pl"]] = o, ph, pl
        setup = pl < o < ph
        out[rows, COL["setup"]] = 1.0 if setup else 0.0
        if not setup:
            continue
        hh, ll = high[a:b], low[a:b]
        hits = np.flatnonzero((hh >= ph + tick) | (ll <= pl - tick))
        if not hits.size:
            continue
        k = int(hits[0])
        up, dn = hh[k] >= ph + tick, ll[k] <= pl - tick
        bar_open = open_[a + k]
        side = 1 if up and (not dn or abs(bar_open - ph) <= abs(bar_open - pl)) else -1
        after = rows[k:]
        out[after, COL["side"]] = side
        out[after, COL["breach_at"]] = epoch_ms[a + k]
        out[after, COL["seg"]] = min(2, int(minute[a + k]) // 20)
        level = ph if side == 1 else pl
        for z_i, zone in enumerate(ZONES):
            med, p75, p90 = ZONE_STATS[hod][zone]
            base, direction = (level, side) if zone == "stretch" else (o, -side)
            col = COL[f"{zone}_near"]
            out[after, col] = base + direction * med * o / 100
            out[after, col + 1] = base + direction * p90 * o / 100
            out[after, col + 2] = base + direction * p75 * o / 100
        back = (ll[k + 1 :] <= o) if side == 1 else (hh[k + 1 :] >= o)
        if back.any():
            j = a + k + 1 + int(np.argmax(back))
            out[j:b, COL["revert_at"]] = epoch_ms[j]
    return out


class HourStats(IndicatorBase):
    """Hour open, prior hour high / low, the first breach and the return to the open."""

    spec = IndicatorSpec(
        id="hour_stats",
        name="Hour Stats",
        description=(
            "Each hour 8:00-16:00 New York: hour open and prior hour high / low. When the "
            "open is inside the prior range, marks the first breach and the return to the "
            "open, with the ES 2016-2025 odds by hour and the MAE / MFE zones."
        ),
        parameters={},
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=lambda params: 120,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = hour_stats(
                epoch_ms, *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close"))
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
