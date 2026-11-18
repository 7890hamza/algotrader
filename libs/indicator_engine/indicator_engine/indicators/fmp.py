"""Fractal Manipulation Projections: how far price usually travels early in each hour.

At the open of every clock hour (New York time) we know, from NQ / ES 1-minute data since 2020, how
far price went from that hour's open after 5, 10, 15, 20, 25 and 30 minutes (toward whichever side
the move closed on). Its standard deviation, sigma, is a yardstick for "a normal push" at that time
of day. The indicator draws the open +/- 0.5, 1 and 1.5 sigma for each of the six time slices; the
chart joins equal-sigma levels into curves that fan out from the open.

Scaling (``scale``):
  * ``adaptive`` (default): the 2020+ sigmas are scaled by how big the same clock hour has been over
    the last 20 sessions versus its 2020+ average, so quiet weeks draw tighter rails and wild weeks
    wider ones. On 2010-2026 data a 1 sigma line was reached 20-29% of the time in every year.
  * ``fixed``: the 2020+ sigmas in points, like the original script. Reached 25% of the time in
    2020-2024 but 56% in 2025-26 on NQ, because NQ's point moves have grown.

The lines are a yardstick, not a signal: after price reached the 1 or 1.5 sigma line it went another
half sigma further about as often as it came back half a sigma (2020-2026).
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from ..instruments import run_on_session_rows
from .base import IndicatorBase
from .fmp_tables import RANGE, SIGMA
from .seiz import market_for
from .session_sdev import _local_ms, to_epoch_ms

NEW_YORK = ZoneInfo("America/New_York")
SLICES = (5, 10, 15, 20, 25, 30)
LOOKBACK = 20
OUTPUTS = ["start", "open", "ratio"] + [f"sig{n}" for n in SLICES]
COL = {name: i for i, name in enumerate(OUTPUTS)}
MS_HOUR = 3_600_000


def _warmup(params: Dict) -> int:
    bar = max(1, int(params.get("_bar_minutes") or 1))
    days = 32 if str(params.get("scale", "adaptive")) == "adaptive" else 1
    return math.ceil(days * 1440 / bar)


def fmp(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    *,
    market: str = "NQ",
    scale: str = "adaptive",
) -> np.ndarray:
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    local = _local_ms(epoch_ms, NEW_YORK)
    offset = local - epoch_ms
    hour_key = local // MS_HOUR
    hour_of_day = (hour_key % 24).astype(int)
    df = pd.DataFrame({"k": hour_key, "hr": hour_of_day, "o": open_, "h": high, "l": low})
    g = df.groupby("k", sort=False)
    first_o = g["o"].transform("first").to_numpy()

    # How big each clock hour has been lately versus its 2020+ average.
    ratio = np.ones(n)
    if scale == "adaptive":
        hours = g.agg(hr=("hr", "first"), h=("h", "max"), l=("l", "min"))
        hours["rng"] = hours["h"] - hours["l"]
        recent = hours.groupby("hr")["rng"].transform(
            lambda x: x.rolling(LOOKBACK, min_periods=5).mean().shift(1))
        base = hours["hr"].map(RANGE[market])
        r = (recent / base).reindex(hour_key).to_numpy()
        ratio = np.where(np.isfinite(r) & (r > 0), r, np.nan)

    table = SIGMA[market]
    known = np.array([h in table for h in hour_of_day])
    ok = known & np.isfinite(first_o) & np.isfinite(ratio)
    out[ok, COL["start"]] = (hour_key * MS_HOUR - offset)[ok]
    out[ok, COL["open"]] = first_o[ok]
    out[ok, COL["ratio"]] = np.round(ratio[ok], 4)
    for s in SLICES:
        sig = np.array([table.get(h, {}).get(s, np.nan) for h in range(24)])[hour_of_day]
        out[ok, COL[f"sig{s}"]] = np.round(sig[ok] * ratio[ok], 2)
    return out


class FMP(IndicatorBase):
    """Fractal Manipulation Projections: sigma rails from each hour's open, 5-30 minutes."""

    spec = IndicatorSpec(
        id="fmp",
        name="Fractal Manipulation Projections",
        description=(
            "How far price usually travels in the first 5-30 minutes of each hour: open +/- 0.5, "
            "1 and 1.5 sigma per time slice, joined into curves, from NQ / ES 1-minute data "
            "since 2020."
        ),
        parameters={
            "scale": {"type": "string", "default": "adaptive", "options": ["adaptive", "fixed"]},
            "sigmas": {"type": "string", "default": "0.5,1,1.5"},
            "slices": {"type": "string", "default": "5,10,15,20,25,30"},
            "curves": {
                "type": "string", "default": "curved", "options": ["curved", "straight", "off"],
            },
            "hours_back": {"type": "int", "default": 3, "min": 1, "max": 6},
            "market": {"type": "string", "default": "auto", "options": ["auto", "NQ", "ES"]},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=_warmup,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        p = {**defaults, **{k: v for k, v in (params or {}).items() if v is not None}}
        idx = {}
        for field in ("open", "high", "low"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        scale = "fixed" if str(p["scale"]).lower() == "fixed" else "adaptive"
        for a in range(n_assets):
            cols = [data.data[:, a, idx[f]] for f in ("open", "high", "low")]
            market = market_for(data.assets[a], p["market"])
            out[:, a, :] = run_on_session_rows(
                data.assets[a], epoch_ms, cols, len(OUTPUTS),
                lambda *c, market=market: fmp(*c, market=market, scale=scale))
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={
                "time": data.time,
                "asset": data.assets,
                "output": np.array(OUTPUTS, dtype=object),
            },
        )


__all__ = ["FMP", "fmp", "SIGMA", "OUTPUTS", "COL"]
