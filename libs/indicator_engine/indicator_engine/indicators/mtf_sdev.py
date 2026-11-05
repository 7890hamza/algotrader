"""MTF SDEV: net change SDEV levels for the 1H, 4H, daily, weekly and monthly candles.

For each timeframe, a candle's net change % = (close - open) / open x 100. 1 SDEV is the
population standard deviation (ddof=0) of the previous ``lookback`` finished candles of that
timeframe (``lookback_m`` for monthly), and the levels are open x (1 +/- k x SDEV / 100) for the
candle that is running. Candles follow the CME day (New York time):

  h1  clock hours           h4  four-hour blocks from 18:00
  d   18:00-17:00 (the CME day, 3 PM-2 PM Pacific)
  w   the week of CME days (opens Sunday 18:00)
  m   the calendar month of CME days

Also, on every bar of a CME day:
  ``pdh`` / ``pdl``   previous CME day high / low;  ``pwh`` / ``pwl`` previous week
  ``pd_touch_h`` ... 1 when the line is not already behind the day's open (Hit arrows)
  ``dr_h`` / ``dr_l`` / ``dr_mid``  the day's range so far and its 50% line
  ``adr``             average range of the previous ``lookback`` CME days
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import MINUTES_PER_DAY, MS_PER_DAY, MS_PER_HOUR, MS_PER_MINUTE, _local_ms, to_epoch_ms

NEW_YORK = ZoneInfo("America/New_York")
TIMEFRAMES = ("h1", "h4", "d", "w", "m")
LEVELS = (0.5, 1.0, 1.5, 2.0)
LEVEL_KEYS = ["open"] + [f"{s}{m:g}" for m in LEVELS for s in ("+", "-")]
PARTS = TIMEFRAMES + ("prior", "range")
DEFAULT_SHOW = "d, w, m, prior, range"
DEFAULT_LEVELS = "0.5, 1, 1.5"
EXTRA = ["pdh", "pdl", "pwh", "pwl", "pd_touch_h", "pd_touch_l", "pw_touch_h", "pw_touch_l",
         "dr_h", "dr_l", "dr_mid", "adr"]
OUTPUTS = [f"{tf}_{k}" for tf in TIMEFRAMES for k in LEVEL_KEYS] + EXTRA
COL = {name: i for i, name in enumerate(OUTPUTS)}
CME_OPEN, CME_CLOSE = 18 * 60, 17 * 60
# Calendar minutes of history per timeframe candle (with weekend / holiday slack).
CANDLE_MINUTES = {"h1": 60 * 1.6, "h4": 240 * 1.6, "d": MINUTES_PER_DAY * 1.45, "w": MINUTES_PER_DAY * 7.3,
                  "m": MINUTES_PER_DAY * 31}


def parse_show(raw: object) -> set[str]:
    names = {p.strip().lower() for p in str(raw or "").replace(";", ",").split(",") if p.strip()}
    unknown = names - set(PARTS)
    if unknown:
        raise ValueError(f"Unknown parts {sorted(unknown)}; choose from {', '.join(PARTS)}")
    return names


def parse_levels(raw: object) -> tuple[float, ...]:
    vals = tuple(float(p) for p in str(raw or "").replace(";", ",").split(",") if p.strip())
    bad = [v for v in vals if v not in LEVELS]
    if bad:
        raise ValueError(f"Levels must be among {LEVELS}")
    return vals


def _warmup(params: Dict) -> int:
    parts = parse_show(params.get("show", DEFAULT_SHOW))
    lookback, lookback_m = int(params.get("lookback", 20)), int(params.get("lookback_m", 12))
    need = MINUTES_PER_DAY * 3.0
    for tf in TIMEFRAMES:
        if tf in parts:
            candles = (lookback_m if tf == "m" else lookback) + 2
            need = max(need, candles * CANDLE_MINUTES[tf])
    if parts & {"range"}:
        need = max(need, (lookback + 2) * CANDLE_MINUTES["d"])
    bar = max(1, int(params.get("_bar_minutes") or 1))
    return math.ceil(need / bar)


def _groups(keys: np.ndarray, valid: np.ndarray) -> list[np.ndarray]:
    rows = np.flatnonzero(valid)
    if not rows.size:
        return []
    k = keys[rows]
    return np.split(rows, np.flatnonzero(k[1:] != k[:-1]) + 1)


def mtf_sdev(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    show: str | set[str] = DEFAULT_SHOW,
    levels: tuple[float, ...] = (0.5, 1.0, 1.5),
    lookback: int = 20,
    lookback_m: int = 12,
) -> np.ndarray:
    parts = show if isinstance(show, set) else parse_show(show)
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    local = _local_ms(epoch_ms, NEW_YORK)
    day = local // MS_PER_DAY
    minute = (local // MS_PER_MINUTE) % MINUTES_PER_DAY
    valid = np.isfinite(open_) & np.isfinite(close) & ~((minute >= CME_CLOSE) & (minute < CME_OPEN))
    cme_day = day + (minute >= CME_OPEN)
    keys = {
        "h1": local // MS_PER_HOUR,
        "h4": cme_day * 6 + ((minute - CME_OPEN) % MINUTES_PER_DAY) // 240,
        "d": cme_day,
        "w": (cme_day + 3) // 7,  # Monday-based weeks; Sunday evening belongs to Monday's week
        "m": cme_day.astype("datetime64[D]").astype("datetime64[M]").astype(np.int64),
    }
    groups = {tf: _groups(keys[tf], valid) for tf in ("d", "w")}
    for tf in TIMEFRAMES:
        if tf not in parts:
            continue
        gs = groups.get(tf) or _groups(keys[tf], valid)
        net = np.array([(close[g[-1]] - open_[g[0]]) / open_[g[0]] * 100 for g in gs])
        lb = lookback_m if tf == "m" else lookback
        base_col = COL[f"{tf}_open"]
        for k in range(1 + lb, len(gs)):  # group 0 may start mid-candle: never used
            sigma = float(np.std(net[k - lb:k]))
            rows = gs[k]
            o = float(open_[rows[0]])
            out[rows, base_col] = o
            for m in levels:
                out[rows, COL[f"{tf}_+{m:g}"]] = o * (1 + m * sigma / 100)
                out[rows, COL[f"{tf}_-{m:g}"]] = o * (1 - m * sigma / 100)
    if "prior" in parts:
        for tf, (hk, lk, th, tl) in (("d", ("pdh", "pdl", "pd_touch_h", "pd_touch_l")),
                                     ("w", ("pwh", "pwl", "pw_touch_h", "pw_touch_l"))):
            gs = groups[tf]
            for k in range(1, len(gs)):
                prev, rows = gs[k - 1], gs[k]
                ph, pl = float(np.nanmax(high[prev])), float(np.nanmin(low[prev]))
                o = float(open_[rows[0]])
                out[rows, COL[hk]], out[rows, COL[lk]] = ph, pl
                out[rows, COL[th]] = 0.0 if o > ph else 1.0
                out[rows, COL[tl]] = 0.0 if o < pl else 1.0
    if "range" in parts:
        gs = groups["d"]
        ranges = np.array([np.nanmax(high[g]) - np.nanmin(low[g]) for g in gs])
        for k, rows in enumerate(gs):
            hi = np.maximum.accumulate(high[rows])
            lo = np.minimum.accumulate(low[rows])
            out[rows, COL["dr_h"]], out[rows, COL["dr_l"]], out[rows, COL["dr_mid"]] = hi, lo, (hi + lo) / 2
            if k > lookback:
                out[rows, COL["adr"]] = float(np.mean(ranges[k - lookback:k]))
    return out


class MtfSDEV(IndicatorBase):
    """1H / 4H / daily / weekly / monthly SDEV levels, prior day / week highs and lows, day range."""

    spec = IndicatorSpec(
        id="mtf_sdev",
        name="MTF SDEV",
        description=(
            "Net change SDEV levels for the running 1H, 4H, daily, weekly and monthly candles "
            "(CME day), the previous day / week high and low, and the day's range with its 50% line."
        ),
        parameters={
            "show": {"type": "string", "default": DEFAULT_SHOW},
            "levels": {"type": "string", "default": DEFAULT_LEVELS},
            "lookback": {"type": "int", "default": 20, "min": 2},
            "lookback_m": {"type": "int", "default": 12, "min": 2},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=_warmup,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        merged = {**defaults, **{k: v for k, v in (params or {}).items() if v is not None}}
        kwargs = dict(show=parse_show(merged["show"]), levels=parse_levels(merged["levels"]),
                      lookback=int(merged["lookback"]), lookback_m=int(merged["lookback_m"]))
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = mtf_sdev(epoch_ms, *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")), **kwargs)
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={"time": data.time, "asset": data.assets, "output": np.array(OUTPUTS, dtype=object)},
        )
