"""SEIZ (Statistical External & Internal Zones), made simple.

Every candle (1H, 4H, daily) either stays inside the previous candle's range or breaks out of it,
on each side. From 18 years of 1-minute futures data (2008-2026, NinjaTrader) we measured, for
each timeframe:

  internal high  how far the high got above the OPEN, on candles that stayed below the prior high
  internal low   how far the low got below the OPEN, on candles that stayed above the prior low
  external high  how far the high went past the PRIOR HIGH, on candles that broke it
  external low   how far the low went past the PRIOR LOW, on candles that broke it

and kept the 50th / 75th / 85th / 99th percentile of each (in % of price). The zones are fixed
when the candle opens (no repaint). Like SEIZ, the internal lines on a side switch off and the
external lines switch on once the candle breaks the prior high / low on that side.

The simple read (what the chart labels say):
  Buy 75% / Sell 75%    3 in 4 candles pull back less than this from the open (internal 75th)
  Stretch 85%           only 15 in 100 breakouts went further than this (external 85th)
  Extreme 99%           only 1 in 100 went further (external 99th)
  Open                  the candle's open (where a normal pullback tends to come back to)

Outputs per timeframe ``tf`` in h1 / h4 / d:
  ``tf_open``, ``tf_ph``, ``tf_pl`` and ``tf_{ih,il,eh,el}{50,75,85,99}`` (16 bands).
``detail="simple"`` fills only open, the 75% internal lines, the 85% / 99% external lines and
the prior high / low; ``detail="full"`` fills all 16 bands.
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
from .session_sdev import (
    MINUTES_PER_DAY,
    MS_PER_DAY,
    MS_PER_HOUR,
    MS_PER_MINUTE,
    _local_ms,
    to_epoch_ms,
)

NEW_YORK = ZoneInfo("America/New_York")
TIMEFRAMES = ("h1", "h4", "d")
PCTS = (50, 75, 85, 99)
ZONES = ("ih", "il", "eh", "el")
CME_OPEN, CME_CLOSE = 18 * 60, 17 * 60

# Percentile tables, % of price. Source: NinjaTrader 1-minute NQ / ES, 2008-01-02 to 2026-11-13,
# stitched front month (roll on volume), candles on the CME day (New York time).
TABLES: dict[str, dict[str, dict[str, tuple[float, float, float, float]]]] = {
    "NQ": {
        "h1": {"ih": (0.0562, 0.1241, 0.1850, 0.6599), "il": (0.0550, 0.1187, 0.1729, 0.6236),
               "eh": (0.0865, 0.1873, 0.2764, 1.0152), "el": (0.0952, 0.2194, 0.3315, 1.2115)},
        "h4": {"ih": (0.1144, 0.2374, 0.3466, 1.1119), "il": (0.1090, 0.2237, 0.3162, 1.0382),
               "eh": (0.2055, 0.4213, 0.5919, 1.8135), "el": (0.2324, 0.5154, 0.7420, 2.3221)},
        "d": {"ih": (0.3982, 0.7603, 1.0175, 2.7487), "il": (0.3139, 0.6156, 0.8301, 2.5434),
              "eh": (0.4754, 0.8917, 1.2383, 3.0255), "el": (0.6289, 1.2030, 1.6225, 4.2491)},
    },
    "ES": {
        "h1": {"ih": (0.0464, 0.1031, 0.1507, 0.5702), "il": (0.0455, 0.0960, 0.1414, 0.5302),
               "eh": (0.0605, 0.1387, 0.2083, 0.8318), "el": (0.0646, 0.1579, 0.2455, 0.9810)},
        "h4": {"ih": (0.0902, 0.1905, 0.2768, 0.9632), "il": (0.0850, 0.1760, 0.2486, 0.8392),
               "eh": (0.1487, 0.3191, 0.4561, 1.5070), "el": (0.1641, 0.3831, 0.5661, 1.9287)},
        "d": {"ih": (0.2921, 0.5911, 0.8236, 2.3070), "il": (0.2563, 0.4960, 0.6499, 2.1174),
              "eh": (0.3697, 0.7086, 0.9983, 2.6898), "el": (0.4787, 0.9339, 1.3028, 3.8631)},
    },
}
NQ_NAMES = ("NQ", "MNQ", "NAS", "NDX", "USTEC", "US100", "XYZ100")

SIMPLE = {"ih75", "il75", "eh85", "el85", "eh99", "el99"}
PER_TF = ["open", "ph", "pl"] + [f"{z}{p}" for z in ZONES for p in PCTS]
OUTPUTS = [f"{tf}_{k}" for tf in TIMEFRAMES for k in PER_TF]
COL = {name: i for i, name in enumerate(OUTPUTS)}
DEFAULT_SHOW = "h1"


def parse_show(raw: object) -> list[str]:
    names = [p.strip().lower() for p in str(raw or "").replace(";", ",").split(",") if p.strip()]
    bad = [n for n in names if n not in TIMEFRAMES]
    if bad:
        raise ValueError(f"Unknown timeframes {bad}; choose from {', '.join(TIMEFRAMES)}")
    return names


def market_for(asset: object, choice: str = "auto") -> str:
    choice = str(choice or "auto").upper()
    if choice in TABLES:
        return choice
    name = str(asset or "").upper()
    return "NQ" if any(k in name for k in NQ_NAMES) else "ES"


def _warmup(params: Dict) -> int:
    # Only the previous candle is needed (the statistics are fixed tables).
    need = {"h1": 60 * 3, "h4": 240 * 3, "d": MINUTES_PER_DAY * 4}
    tfs = parse_show(params.get("show", DEFAULT_SHOW)) or ["h1"]
    bar = max(1, int(params.get("_bar_minutes") or 1))
    return math.ceil(max(need[t] for t in tfs) / bar)


def _groups(keys: np.ndarray, valid: np.ndarray) -> list[np.ndarray]:
    rows = np.flatnonzero(valid)
    if not rows.size:
        return []
    k = keys[rows]
    return np.split(rows, np.flatnonzero(k[1:] != k[:-1]) + 1)


def _tick_round(x: float, tick: float) -> float:
    return round(round(x / tick) * tick, 6) if tick > 0 else x


def seiz(  # noqa: C901 - one loop per zone, kept flat to read like the docstring
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    *,
    market: str = "NQ",
    show: list[str] | None = None,
    detail: str = "simple",
    auto_switch: bool = True,
    tick: float = 0.25,
) -> np.ndarray:
    show = list(TIMEFRAMES) if show is None else show
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    table = TABLES[market]
    local = _local_ms(np.asarray(epoch_ms, dtype=np.int64), NEW_YORK)
    day = local // MS_PER_DAY
    minute = (local // MS_PER_MINUTE) % MINUTES_PER_DAY
    valid = np.isfinite(open_) & np.isfinite(high) & np.isfinite(low) & ~((minute >= CME_CLOSE) & (minute < CME_OPEN))
    cme_day = day + (minute >= CME_OPEN)
    keys = {"h1": local // MS_PER_HOUR,
            "h4": cme_day * 6 + ((minute - CME_OPEN) % MINUTES_PER_DAY) // 240,
            "d": cme_day}
    full = str(detail).lower() == "full"
    for tf in show:
        gs = _groups(keys[tf], valid)
        t = table[tf]
        for k in range(1, len(gs)):
            prev, rows = gs[k - 1], gs[k]
            ph, pl = float(np.nanmax(high[prev])), float(np.nanmin(low[prev]))
            o = float(open_[rows[0]])
            out[rows, COL[f"{tf}_open"]] = o
            out[rows, COL[f"{tf}_ph"]] = ph
            out[rows, COL[f"{tf}_pl"]] = pl
            inside = pl < o < ph
            # running extremes, to switch internal -> external once a side breaks
            run_hi = np.maximum.accumulate(high[rows])
            run_lo = np.minimum.accumulate(low[rows])
            broke_hi = run_hi >= ph if auto_switch else np.zeros(len(rows), bool)
            broke_lo = run_lo <= pl if auto_switch else np.zeros(len(rows), bool)
            for i, p in enumerate(PCTS):
                for z in ZONES:
                    key = f"{z}{p}"
                    if not full and key not in SIMPLE:
                        continue
                    pct = t[z][i] / 100
                    if z == "ih":
                        if not inside:
                            continue
                        lvl = _tick_round(o * (1 + pct), tick)
                        if lvl >= ph:
                            continue
                        vis = ~broke_hi
                    elif z == "il":
                        if not inside:
                            continue
                        lvl = _tick_round(o * (1 - pct), tick)
                        if lvl <= pl:
                            continue
                        vis = ~broke_lo
                    elif z == "eh":
                        lvl = _tick_round(ph + o * pct, tick)
                        vis = broke_hi | (not auto_switch) | (not inside)
                    else:
                        lvl = _tick_round(pl - o * pct, tick)
                        vis = broke_lo | (not auto_switch) | (not inside)
                    vis = np.broadcast_to(vis, rows.shape)
                    out[rows[vis], COL[f"{tf}_{key}"]] = lvl
    return out


class SEIZ(IndicatorBase):
    """Statistical external & internal zones for the running 1H / 4H / daily candle."""

    spec = IndicatorSpec(
        id="seiz",
        name="SEIZ Zones",
        description=(
            "How far a 1H / 4H / daily candle usually pulls back from its open (Buy / Sell 75%) and "
            "how far it usually runs past the prior high / low (Stretch 85%, Extreme 99%), from "
            "18 years of NQ / ES data."
        ),
        parameters={
            "show": {"type": "string", "default": DEFAULT_SHOW},
            "detail": {"type": "string", "default": "simple"},
            "market": {"type": "string", "default": "auto"},
            "auto_switch": {"type": "string", "default": "on"},
            "tick": {"type": "float", "default": 0.25},
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
        show = parse_show(merged["show"])
        idx = {}
        for field in ("open", "high", "low"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = seiz(
                epoch_ms, *(data.data[:, a, idx[f]] for f in ("open", "high", "low")),
                market=market_for(data.assets[a], merged["market"]), show=show,
                detail=str(merged["detail"]), auto_switch=str(merged["auto_switch"]).strip().lower() not in ("off", "false", "0", "no"),
                tick=float(merged["tick"]),
            )
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={"time": data.time, "asset": data.assets, "output": np.array(OUTPUTS, dtype=object)},
        )


__all__ = ["SEIZ", "seiz", "TABLES", "market_for"]
