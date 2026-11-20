"""Setups: the seven indicator pairings that gave the cleanest 10-point ES moves in 2026.

Found by backtesting every pair of our indicators' signals on ES, Jan 1 - Nov 13 2026 (chosen on
Jan-Jun, checked on Jul-Nov): a setup fires on the 5-minute bar where both of its conditions first
line up; the trade enters at the next bar, aims for ``target`` points and gives ``stop`` points,
and closes at the market after ``hold`` minutes. One trade at a time per setup.

  A long   Double high break             above prior RTH high (Breaks) + prior week high (MTF)
  B long   Quick push on a calm day      SEIZ 15m broke last high + SEIZ daily internal 75+ push
  C long   Month up, AM dip reclaimed    above month open (MTF) + AM TBR back to open from below
  D short  Day stretched, hour breaks    past day -1 SD (MTF) + broke prior hour low (Hour Stats)
  E short  4H breakdown + NY stretched   SEIZ 4h broke its last low + NY net change past -1 SD
  F short  Below yesterday, AM pop fails below prior day low (MTF) + AM TBR back to open from above
  G short  Spike fails under yesterday   hour stretched past +1.5 sigma (FMP) + below prior day low

Outputs, per setup X (only on the bar a trade starts): X_dir (+1 / -1), X_entry, X_exit_ms,
X_pts (after ``cost``), X_how (1 target, -1 stop, 0 time), X_l1 / X_l2 (the two trigger levels).
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pandas as pd

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import to_epoch_ms

SETUPS = ["A", "B", "C", "D", "E", "F", "G"]
FIELDS = ["dir", "entry", "exit_ms", "pts", "how", "l1", "l2"]
OUTPUTS = [f"{s}_{f}" for s in SETUPS for f in FIELDS]
COL = {name: i for i, name in enumerate(OUTPUTS)}
COOLDOWN = 12  # 5-minute bars (one position at a time per setup)
FIVE_MIN = 300_000


def _warmup(params: Dict) -> int:
    bar = max(1, int(params.get("_bar_minutes") or 1))
    return math.ceil(40 * 1440 / bar)  # month open, 20-day SDEV, 20-session FMP scaling


def _five_minute(epoch_ms: np.ndarray, o, h, lo, c) -> pd.DataFrame:
    idx = pd.to_datetime(epoch_ms, unit="ms", utc=True)
    df = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)
    how = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df.resample("5min").agg(how).dropna()


def _run(ind, b: pd.DataFrame, asset: str, params: Dict | None = None) -> pd.DataFrame:
    bt = BarTensor(
        data=b[["open", "high", "low", "close"]].to_numpy()[:, None, :],
        time=b.index.tz_localize(None).values.astype("datetime64[ns]"),
        assets=np.array([asset], dtype=object),
        fields=np.array(["open", "high", "low", "close"], dtype=object),
    )
    r = ind.batch(bt, params or {})
    return pd.DataFrame(r.data[:, 0, :], columns=ind.spec.outputs, index=b.index)


def signals(b: pd.DataFrame, asset: str) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Per setup on 5-minute bars: (on, level 1, level 2)."""
    from . import FMP, SEIZ, AlnTBR, AmTBR, Breaks, HourStats, MtfSDEV, SessionSDEV  # noqa: F401

    c = b.close.to_numpy()
    close_ms = b.index.as_unit("ns").asi8 // 1_000_000 + FIVE_MIN

    def at(x) -> np.ndarray:
        x = np.asarray(x, float)
        return np.isfinite(x) & (x <= close_ms)

    def zed(op, one) -> np.ndarray:
        op, one = np.asarray(op, float), np.asarray(one, float)
        return (c - op) / np.where(np.abs(one - op) > 0, one - op, np.nan)

    mtf = _run(MtfSDEV(), b, asset)
    brk = _run(Breaks(), b, asset)
    seiz = _run(SEIZ(), b, asset, {"zone_tf": "1h"})
    am = _run(AmTBR(), b, asset)
    hs = _run(HourStats(), b, asset)
    ssd = _run(SessionSDEV(), b, asset)
    fm = _run(FMP(), b, asset)
    with np.errstate(invalid="ignore", divide="ignore"):
        hi15, lo15 = seiz["d_15m_hi"].to_numpy(), seiz["d_15m_lo"].to_numpy()
        hid, lod = seiz["d_1d_hi"].to_numpy(), seiz["d_1d_lo"].to_numpy()
        hi4, lo4 = seiz["d_4h_hi"].to_numpy(), seiz["d_4h_lo"].to_numpy()
        a_side = np.nan_to_num(am.touch_side.to_numpy())
        a_back = at(am.revert_at)
        h_side = np.nan_to_num(hs.side.to_numpy())
        fz = (c - fm.open.to_numpy()) / fm.sig30.to_numpy()
        pdl = mtf.pdl.to_numpy()
        out = {
            "A": (at(brk.rth_hit_h) & (c > brk.prth_h.to_numpy()) & (c > mtf.pwh.to_numpy()),
                  brk.prth_h.to_numpy(), mtf.pwh.to_numpy()),
            "B": ((hi15 >= 100) & ~(lo15 >= 100) & (hid >= 75) & (hid < 100) & (lod < 50),
                  mtf.d_open.to_numpy(), np.full(len(c), np.nan)),
            "C": ((zed(mtf.m_open, mtf["m_+1"]) > 0) & (a_side < 0) & a_back,
                  am.open.to_numpy(), mtf.m_open.to_numpy()),
            "D": ((zed(mtf.d_open, mtf["d_+1"]) < -1) & (h_side < 0) & at(hs.breach_at)
                  & ~at(hs.revert_at), mtf["d_-1"].to_numpy(), hs.pl.to_numpy()),
            "E": ((lo4 >= 100) & ~(hi4 >= 100) & (zed(ssd["open"], ssd["+1"]) < -1),
                  ssd["-1"].to_numpy(), np.full(len(c), np.nan)),
            "F": ((c < pdl) & (a_side > 0) & a_back, am.open.to_numpy(), pdl),
            "G": ((fz > 1.5) & (c < pdl), fm.open.to_numpy() + 1.5 * fm.sig30.to_numpy(), pdl),
        }
    return {k: (np.nan_to_num(v[0].astype(float)) > 0, v[1], v[2]) for k, v in out.items()}


def _simulate(j, d, epoch_ms, open_, high, low, close, target, stop, hold):
    """Enter at bar j's open; first of target / stop wins (stop when both hit in one bar)."""
    n = len(epoch_ms)
    e = float(open_[j])
    end = epoch_ms[j] + hold * 60_000
    m = j
    while m < n and epoch_ms[m] < end:
        if (low[m] <= e - stop) if d > 0 else (high[m] >= e + stop):
            return e, -stop, -1, int(epoch_ms[m])
        if (high[m] >= e + target) if d > 0 else (low[m] <= e - target):
            return e, target, 1, int(epoch_ms[m])
        m += 1
    last_bar = max(j, m - 1)
    return e, (float(close[last_bar]) - e) * d, 0, int(epoch_ms[last_bar])


def setups(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    asset: str = "ES",
    target: float = 10.0,
    stop: float = 3.0,
    hold: int = 60,
    cost: float = 0.5,
) -> np.ndarray:
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan)
    if n < 2:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    b = _five_minute(epoch_ms, open_, high, low, close)
    if len(b) < 50:
        return out
    sig = signals(b, asset)
    close_ms = b.index.as_unit("ns").asi8 // 1_000_000 + FIVE_MIN
    dirs = {"A": 1, "B": 1, "C": 1, "D": -1, "E": -1, "F": -1, "G": -1}
    for sid, (on, l1, l2) in sig.items():
        d = dirs[sid]
        fresh = on & ~np.r_[False, on[:-1]]
        last = -(10**9)
        for k in np.where(fresh)[0]:
            if k - last < COOLDOWN:
                continue
            j = int(np.searchsorted(epoch_ms, close_ms[k]))  # first chart bar after the close
            if j >= n:
                continue
            last = k
            bars = (epoch_ms, open_, high, low, close)
            e, pts, how, exit_ms = _simulate(j, d, *bars, target, stop, hold)
            row = {"dir": d, "entry": e, "exit_ms": exit_ms, "pts": round(pts - cost, 2),
                   "how": how, "l1": l1[k], "l2": l2[k]}
            for f, v in row.items():
                out[j, COL[f"{sid}_{f}"]] = v
    return out


class Setups(IndicatorBase):
    """The seven 2026 ES setups: where they fired and how each trade ended."""

    spec = IndicatorSpec(
        id="setups",
        name="Setups",
        description=(
            "The seven indicator pairings that gave the cleanest 10-point ES moves in 2026: where "
            "each fired, its 10-point target and 3-point stop, and how the trade ended."
        ),
        parameters={
            "target": {"type": "float", "default": 10.0},
            "stop": {"type": "float", "default": 3.0},
            "hold": {"type": "int", "default": 60, "min": 5, "max": 480},
            "cost": {"type": "float", "default": 0.5},
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
        p = {**defaults, **{k: v for k, v in (params or {}).items() if v is not None}}
        idx = {f: int(np.where(data.fields == f)[0][0]) for f in ("open", "high", "low", "close")}
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan)
        for a in range(n_assets):
            cols = [data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")]
            out[:, a, :] = setups(
                epoch_ms, *cols, asset=str(data.assets[a]), target=float(p["target"]),
                stop=float(p["stop"]), hold=int(p["hold"]), cost=float(p["cost"]),
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


__all__ = ["Setups", "setups", "SETUPS", "OUTPUTS", "COL", "signals"]
