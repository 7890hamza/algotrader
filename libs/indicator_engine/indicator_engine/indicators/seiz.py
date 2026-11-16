"""SEIZ: Statistical External & Internal Zones.

A candle can only do four things on its two sides: its high stays inside the last candle's range
(internal high) or pushes above it (external high), and the same for its low. For every timeframe
from 15m to 1W we measured, on 18 years of NQ / ES 1-minute data, how far each of the four went:

  internal high / low   from the candle's OPEN, on candles whose extreme stayed inside the last range
  external high / low   past the LAST HIGH / LOW, on candles that broke it

Each zone is split into four percentile bands, 50th / 75th / 85th / 99th: the deeper the colour,
the rarer the move. Zones are set when the candle opens and never move; with auto switching the
internal zone on a side gives way to the external zone the moment the last high / low breaks.

Stat Zone (optional): one box per side from the 25th to the 75th percentile of how far a candle's
high / low got from its open, with a dashed line at the median: where the timeframe typically gets to.

Dashboard: for every timeframe, the most significant band reached so far on each side
(``int_pct`` / ``100 + ext_pct``; 0 = none yet, 100 = external but short of the 50th) and how much
of the candle has completed.
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
from .base import IndicatorBase
from .seiz_frames import TIMEFRAMES, frame_keys, in_session
from .seiz_tables import TABLES
from .session_sdev import _local_ms, to_epoch_ms

NEW_YORK = ZoneInfo("America/New_York")
PCTS = (50, 75, 85, 99)
ZONES = ("ih", "il", "eh", "el")
NQ_NAMES = ("NQ", "MNQ", "NAS", "NDX", "USTEC", "US100", "XYZ100")
TF_MINUTES = {"15m": 15, "30m": 30, "1d": 1380, "1w": 6900} | {f"{h}h": 60 * h for h in range(1, 13)}

ZONE_OUT = ["start", "end", "open", "ph", "pl"] + [f"{z}{p}" for z in ZONES for p in PCTS] + [
    "st_h_lo", "st_h_mid", "st_h_hi", "st_l_hi", "st_l_mid", "st_l_lo"]
# per timeframe: band codes, progress, and the candle itself (open / high / low / now) measured in
# the last candle's range (0 = its low, 1 = its high) for the dashboard's candle strip
DASH_OUT = [f"d_{tf}_{k}" for tf in TIMEFRAMES for k in ("hi", "lo", "pg", "o", "h", "l", "c")]
OUTPUTS = ZONE_OUT + DASH_OUT
COL = {name: i for i, name in enumerate(OUTPUTS)}
DEFAULT_TF = "1h"


def market_for(asset: object, choice: str = "auto") -> str:
    choice = str(choice or "auto").upper()
    if choice in TABLES:
        return choice
    name = str(asset or "").upper()
    return "NQ" if any(k in name for k in NQ_NAMES) else "ES"


def parse_tf(raw: object) -> str:
    tf = str(raw or DEFAULT_TF).strip().lower().replace("min", "m").replace("hr", "h")
    tf = {"d": "1d", "day": "1d", "daily": "1d", "w": "1w", "week": "1w", "weekly": "1w", "60m": "1h", "240m": "4h"}.get(tf, tf)
    if tf not in TIMEFRAMES:
        raise ValueError(f"Unknown zone timeframe {raw!r}; choose from {', '.join(TIMEFRAMES)}")
    return tf


def _on(raw: object) -> bool:
    return str(raw).strip().lower() not in ("off", "false", "0", "no", "")


def _warmup(params: Dict) -> int:
    tf = parse_tf(params.get("zone_tf", DEFAULT_TF))
    need = TF_MINUTES[tf] * 2 + 60
    if _on(params.get("dashboard", "on")):
        need = max(need, TF_MINUTES["1w"] * 2 + 60 * 48)
    bar = max(1, int(params.get("_bar_minutes") or 1))
    return math.ceil(need / bar)


def _candles(local: np.ndarray, valid: np.ndarray, tf: str, o, h, lo):
    """Per bar: candle start / end (local ms), candle open, prior high / low, running high / low."""
    key, start, end = frame_keys(local, tf)
    df = pd.DataFrame({"k": key, "o": o, "h": h, "l": lo})
    df.loc[~valid, ["o", "h", "l"]] = np.nan
    g = df.groupby("k", sort=False)
    first_o = g["o"].transform("first").to_numpy()
    run_hi = g["h"].cummax().to_numpy()
    run_lo = g["l"].cummin().to_numpy()
    agg = g.agg(h=("h", "max"), l=("l", "min"))
    order = pd.unique(key)
    agg = agg.reindex(order)
    prev_h = pd.Series(agg["h"].shift(1).to_numpy(), index=order)
    prev_l = pd.Series(agg["l"].shift(1).to_numpy(), index=order)
    return start, end, first_o, prev_h.reindex(key).to_numpy(), prev_l.reindex(key).to_numpy(), run_hi, run_lo


def _round(x: np.ndarray, tick: float) -> np.ndarray:
    return np.round(np.round(x / tick) * tick, 6) if tick > 0 else x


def _code(value_pct: np.ndarray, bands: tuple, external: bool) -> np.ndarray:
    """Most significant percentile passed: 0 / 50 / 75 / 85 / 99 (+100 when external)."""
    reached = np.zeros(value_pct.shape)
    for p, b in zip(PCTS, bands):
        reached = np.where(value_pct >= b, p, reached)
    return reached + (100 if external else 0)


def seiz(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    *,
    market: str = "NQ",
    zone_tf: str = DEFAULT_TF,
    auto_switch: bool = True,
    stat_zone: bool = False,
    dashboard: bool = True,
    tick: float = 0.25,
    close: np.ndarray | None = None,
) -> np.ndarray:
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    local = _local_ms(epoch_ms, NEW_YORK)
    offset = local - epoch_ms
    valid = in_session(local) & np.isfinite(open_) & np.isfinite(high) & np.isfinite(low)
    table = TABLES[market]

    # ---- zones for the chosen timeframe ----
    start, end, o, ph, pl, run_hi, run_lo = _candles(local, valid, zone_tf, open_, high, low)
    t = table[zone_tf]
    ok = valid & np.isfinite(ph) & np.isfinite(o)
    inside = ok & (o < ph) & (o > pl)
    broke_hi = run_hi >= ph
    broke_lo = run_lo <= pl
    show_ih = inside & (~broke_hi if auto_switch else True)
    show_il = inside & (~broke_lo if auto_switch else True)
    show_eh = ok & ((broke_hi | ~inside) if auto_switch else True)
    show_el = ok & ((broke_lo | ~inside) if auto_switch else True)
    out[ok, COL["start"]] = (start - offset)[ok]
    out[ok, COL["end"]] = (end - offset)[ok]
    out[ok, COL["open"]] = o[ok]
    out[ok, COL["ph"]] = ph[ok]
    out[ok, COL["pl"]] = pl[ok]
    for i, p in enumerate(PCTS):
        lv = {"ih": _round(o * (1 + t["ih"][i] / 100), tick), "il": _round(o * (1 - t["il"][i] / 100), tick),
              "eh": _round(ph + o * t["eh"][i] / 100, tick), "el": _round(pl - o * t["el"][i] / 100, tick)}
        # an internal band can't reach past the last high / low (that's external territory)
        lv["ih"] = np.where(lv["ih"] < ph, lv["ih"], ph)
        lv["il"] = np.where(lv["il"] > pl, lv["il"], pl)
        for z, mask in (("ih", show_ih), ("il", show_il), ("eh", show_eh), ("el", show_el)):
            out[mask, COL[f"{z}{p}"]] = lv[z][mask]
    if stat_zone:
        sh, sl = t["sh"], t["sl"]
        for k, q in (("st_h_lo", sh[0]), ("st_h_mid", sh[1]), ("st_h_hi", sh[2])):
            out[ok, COL[k]] = _round(o * (1 + q / 100), tick)[ok]
        for k, q in (("st_l_hi", sl[0]), ("st_l_mid", sl[1]), ("st_l_lo", sl[2])):
            out[ok, COL[k]] = _round(o * (1 - q / 100), tick)[ok]

    # ---- dashboard: every timeframe ----
    if dashboard:
        for tf in TIMEFRAMES:
            s, e, o2, ph2, pl2, hi2, lo2 = _candles(local, valid, tf, open_, high, low)
            tt = table[tf]
            ok2 = valid & np.isfinite(ph2) & np.isfinite(o2)
            in2 = (o2 < ph2) & (o2 > pl2)
            hi_code = np.where(hi2 >= ph2, _code((hi2 - ph2) / o2 * 100, tt["eh"], True),
                               np.where(in2, _code((hi2 - o2) / o2 * 100, tt["ih"], False), 0))
            lo_code = np.where(lo2 <= pl2, _code((pl2 - lo2) / o2 * 100, tt["el"], True),
                               np.where(in2, _code((o2 - lo2) / o2 * 100, tt["il"], False), 0))
            progress = np.clip((local + 60_000 - s) / np.maximum(e - s, 1), 0, 1) * 100
            out[ok2, COL[f"d_{tf}_hi"]] = hi_code[ok2]
            out[ok2, COL[f"d_{tf}_lo"]] = lo_code[ok2]
            out[ok2, COL[f"d_{tf}_pg"]] = np.round(progress[ok2])
            span = np.where(ph2 - pl2 > 0, ph2 - pl2, np.nan)
            now = np.asarray(close if close is not None else open_, dtype=float)
            for k, v in (("o", o2), ("h", hi2), ("l", lo2), ("c", now)):
                out[ok2, COL[f"d_{tf}_{k}"]] = np.round((v - pl2) / span, 3)[ok2]
    return out


class SEIZ(IndicatorBase):
    """Statistical external & internal zones, 15m to 1W, with the Stat Zone and dashboard."""

    spec = IndicatorSpec(
        id="seiz",
        name="SEIZ",
        description=(
            "Statistical External & Internal Zones: how far each candle usually goes, inside or beyond "
            "the last candle, on sixteen timeframes (15m to 1W), from 18 years of NQ / ES data."
        ),
        parameters={
            "zone_tf": {"type": "string", "default": DEFAULT_TF, "options": list(TIMEFRAMES)},
            "auto_switch": {"type": "string", "default": "on", "options": ["on", "off"]},
            "stat_zone": {"type": "string", "default": "off", "options": ["off", "on"]},
            "dashboard": {"type": "string", "default": "on", "options": ["on", "off"]},
            "market": {"type": "string", "default": "auto", "options": ["auto", "NQ", "ES"]},
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
        p = {**defaults, **{k: v for k, v in (params or {}).items() if v is not None}}
        idx = {}
        for field in ("open", "high", "low"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        ci = int(np.where(data.fields == "close")[0][0]) if "close" in data.fields else None
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = seiz(
                epoch_ms, *(data.data[:, a, idx[f]] for f in ("open", "high", "low")),
                market=market_for(data.assets[a], p["market"]), zone_tf=parse_tf(p["zone_tf"]),
                auto_switch=_on(p["auto_switch"]), stat_zone=_on(p["stat_zone"]),
                dashboard=_on(p["dashboard"]), tick=float(p["tick"]),
                close=data.data[:, a, ci] if ci is not None else None,
            )
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={"time": data.time, "asset": data.assets, "output": np.array(OUTPUTS, dtype=object)},
        )


__all__ = ["SEIZ", "seiz", "TABLES", "market_for", "parse_tf", "OUTPUTS", "COL"]
