"""Breaks: IB, RTH and ETH breaks (nqstats.com/ib-breaks and /rth_breaks) measured on ES.

All windows are New York time (the same clock times as Pacific + 3 hours):

* RTH  09:30-16:00 (6:30 AM-1 PM Pacific). pRTH = the previous RTH session's high / low.
* IB   09:30-10:30 (6:30-7:30 AM Pacific), the first RTH hour.
* ETH  18:00-17:00 (3 PM-2 PM Pacific), the full Globex day. pETH = the previous one.

A break (a "hit") is a trade at least 1 tick past the level.

Outputs, NaN where a part is off or has no data:

RTH (on the RTH bars of each day that has a previous RTH session)
  ``prth_h`` / ``prth_l``   previous RTH high / low
  ``rth_setup``             +1 opened above pRTH high, -1 below pRTH low, 0 inside
  ``rth_third``             inside days: +1 upper third, 0 middle, -1 lower third of pRTH
  ``rth_touch_h`` / ``_l``  1 when that line can be "hit" today (not already behind the open)
  ``rth_hit_h`` / ``_l``    epoch ms of the first hit, from that bar on
  ``rth_box_h`` / ``_l``    the day's own RTH high / low once the next session has started
                            (the see-through pRTH box)

IB
  ``ib_box_h`` / ``_l``     running high / low during 09:30-10:30 (the IB box)
  ``ib_h`` / ``ib_l`` / ``ib_mid``  from 10:30 to 16:00
  ``ib_side``               +1 the 10:29 close is above the mid, -1 below, 0 on it
  ``ib_valid``              1 when the 10:30 bar opens inside the IB (the stats' filter)
  ``ib_hit_h`` / ``_l``     epoch ms of the first hit, from that bar on
  ``ib_ext_med`` / ``ib_ext_p75``  after the first break: how far price usually runs past
                            the broken side (0.62 and 1.18 IB ranges, ES 2016-2025)

ETH (on every bar of each ETH day that has a previous ETH day)
  ``peth_h`` / ``peth_l``, ``eth_setup`` (+1 / -1 open outside, 0 inside), ``eth_third``,
  ``eth_touch_h`` / ``_l``, ``eth_hit_h`` / ``_l`` as for RTH; ``eth_box_h`` / ``_l`` the day's
  own range once a later ETH day exists.

Retracement (RTH bars after the IB window; the IB is the first leg; see ``_retrace``)
  ``rt_dir`` trend (+1 / -1), ``rt_start`` / ``rt_end`` the current leg (prices) and
  ``rt_start_at`` / ``rt_end_at`` (epoch ms), ``rt_zone`` the zone number, ``rt_out_at`` /
  ``rt_out_px`` where price came back out of the zone, ``rt_res`` +1 / -1 once that zone
  settles, ``rt_flip_at`` the latest trend change (epoch ms).
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from zoneinfo import ZoneInfo

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import MINUTES_PER_DAY, MS_PER_DAY, MS_PER_MINUTE, _local_ms, to_epoch_ms

NEW_YORK = ZoneInfo("America/New_York")
TICK = 0.25
RTH_START, RTH_END, IB_END = 9 * 60 + 30, 16 * 60, 10 * 60 + 30
ETH_START, ETH_END = 18 * 60, 17 * 60
# How far past the broken IB side price ran (in IB ranges), ES 2016-2025: median, 75th pct.
IB_EXTENSION = (0.62, 1.18)
PARTS = ("rth", "ib", "eth", "targets", "retrace")
DEFAULT_SHOW = "rth, ib, eth, targets, retrace"
RETRACE_ZONE = (0.4, 0.6)

OUTPUTS = [
    "prth_h", "prth_l", "rth_setup", "rth_third", "rth_touch_h", "rth_touch_l", "rth_hit_h", "rth_hit_l",
    "rth_box_h", "rth_box_l",
    "ib_box_h", "ib_box_l", "ib_h", "ib_l", "ib_mid", "ib_side", "ib_valid", "ib_hit_h", "ib_hit_l",
    "ib_ext_med", "ib_ext_p75",
    "peth_h", "peth_l", "eth_setup", "eth_third", "eth_touch_h", "eth_touch_l", "eth_hit_h", "eth_hit_l",
    "eth_box_h", "eth_box_l",
    "rt_dir", "rt_start", "rt_end", "rt_zone", "rt_start_at", "rt_end_at", "rt_out_at", "rt_out_px", "rt_res",
    "rt_flip_at",
]
COL = {name: i for i, name in enumerate(OUTPUTS)}


def parse_show(raw: object) -> set[str]:
    names = {p.strip().lower() for p in str(raw or "").replace(";", ",").split(",") if p.strip()}
    unknown = names - set(PARTS)
    if unknown:
        raise ValueError(f"Unknown parts {sorted(unknown)}; choose from {', '.join(PARTS)}")
    return names


def _groups(keys: np.ndarray, mask: np.ndarray) -> list[np.ndarray]:
    """Row indices of each run of equal ``keys`` among the rows where ``mask`` is set."""
    rows = np.flatnonzero(mask)
    if not rows.size:
        return []
    k = keys[rows]
    cuts = np.flatnonzero(k[1:] != k[:-1]) + 1
    return np.split(rows, cuts)


def _third(o: float, lo: float, hi: float) -> float:
    pos = (o - lo) / (hi - lo) if hi > lo else 0.5
    return 1.0 if pos >= 2 / 3 else -1.0 if pos <= 1 / 3 else 0.0


def _levels(out, rows, high, low, open_, epoch_ms, ph, pl, cols, tick) -> None:
    """Prior high / low, where the open sits, which lines can be hit and the first hits."""
    h_col, l_col, setup_col, third_col, th_col, tl_col, hh_col, hl_col = cols
    o = float(open_[rows[0]])
    out[rows, COL[h_col]], out[rows, COL[l_col]] = ph, pl
    setup = 1.0 if o > ph else -1.0 if o < pl else 0.0
    out[rows, COL[setup_col]] = setup
    if setup == 0.0:
        out[rows, COL[third_col]] = _third(o, pl, ph)
    out[rows, COL[th_col]] = 0.0 if setup == 1.0 else 1.0
    out[rows, COL[tl_col]] = 0.0 if setup == -1.0 else 1.0
    for col, hits in ((hh_col, high[rows] >= ph + tick), (hl_col, low[rows] <= pl - tick)):
        if hits.any():
            k = int(np.argmax(hits))
            out[rows[k:], COL[col]] = epoch_ms[rows[k]]


def _retrace(out, rows, ib_rows, post, high, low, open_, close, epoch_ms, tick) -> None:
    """The IB is the first leg; then each leg, its 40-60% zone, the "Out" and trend changes.

    When the IB window ends, its direction comes from which extreme printed last: low first,
    then high = an up leg (IB low -> IB high), the reverse = a down leg (same candle: its close vs
    open). A pullback that reaches the 40% line, followed by a new extreme, starts a new leg from
    the pullback's extreme; shallower pullbacks just extend the leg. "Out" = the first close back
    past the 40% line after touching it (not on the touching bar); it wins (+1) when a new extreme
    comes first and fails (-1) when price goes past 100% (the leg's start), which flips the trend.
    """
    c = {k: COL[k] for k in OUTPUTS if k.startswith("rt_")}
    hi_k, lo_k = int(np.argmax(high[ib_rows])), int(np.argmin(low[ib_rows]))
    hi_r, lo_r = int(ib_rows[hi_k]), int(ib_rows[lo_k])
    if hi_r != lo_r:
        trend = 1 if hi_r > lo_r else -1
    else:
        trend = 1 if close[hi_r] >= open_[hi_r] else -1
    if trend == 1:
        start, start_r, end, end_r = float(low[lo_r]), lo_r, float(high[hi_r]), hi_r
    else:
        start, start_r, end, end_r = float(high[hi_r]), hi_r, float(low[lo_r]), lo_r
    touched = False
    retr: tuple[float, int] | None = None
    zones: list[dict] = [{"rows": [], "touched": None, "out": None, "res": None}]
    flip_at = np.nan

    def write(r: int) -> None:
        z = zones[-1]
        z["rows"].append(r)
        out[r, c["rt_dir"]] = trend
        out[r, c["rt_start"]], out[r, c["rt_end"]] = start, end
        out[r, c["rt_zone"]] = len(zones) - 1
        out[r, c["rt_start_at"]], out[r, c["rt_end_at"]] = epoch_ms[start_r], epoch_ms[end_r]
        if z["out"] is not None:
            out[r, c["rt_out_at"]], out[r, c["rt_out_px"]] = epoch_ms[z["out"][0]], z["out"][1]
        out[r, c["rt_flip_at"]] = flip_at

    def resolve(z: dict, res: int) -> None:
        if z["out"] is not None and z["res"] is None:
            z["res"] = res
            out[z["rows"], c["rt_res"]] = res

    for r in post:
        s = trend
        if (s == 1 and low[r] < start - tick) or (s == -1 and high[r] > start + tick):
            resolve(zones[-1], -1)
            flip_at = float(epoch_ms[r])
            trend = -s
            start, start_r = end, end_r
            end, end_r = float(low[r] if s == 1 else high[r]), int(r)
            touched, retr = False, None
            zones.append({"rows": [], "touched": None, "out": None, "res": None})
            write(r)
            continue
        if (s == 1 and high[r] > end) or (s == -1 and low[r] < end):
            if touched and retr is not None:
                resolve(zones[-1], 1)
                start, start_r = retr
                end, end_r = float(high[r] if s == 1 else low[r]), int(r)
                zones.append({"rows": [], "touched": None, "out": None, "res": None})
            else:
                end, end_r = float(high[r] if s == 1 else low[r]), int(r)
            touched, retr = False, None
        else:
            ex = float(low[r] if s == 1 else high[r])
            if retr is None or (ex < retr[0] if s == 1 else ex > retr[0]):
                retr = (ex, int(r))
            p40 = end - RETRACE_ZONE[0] * (end - start)
            z = zones[-1]
            if not touched and (low[r] <= p40 if s == 1 else high[r] >= p40):
                touched = True
                z["touched"] = int(r)
            if touched and z["out"] is None and z["touched"] != r and (close[r] > p40 if s == 1 else close[r] < p40):
                z["out"] = (int(r), float(close[r]))
        write(r)


def breaks(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    show: str | set[str] = DEFAULT_SHOW,
    tick: float = TICK,
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)); see the module docstring."""
    parts = show if isinstance(show, set) else parse_show(show)
    n = len(epoch_ms)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    local = _local_ms(epoch_ms, NEW_YORK)
    day = local // MS_PER_DAY
    minute = (local // MS_PER_MINUTE) % MINUTES_PER_DAY
    weekday = (day + 3) % 7  # 1970-01-01 was a Thursday; Monday == 0
    diffs = np.diff(epoch_ms)
    bar_min = max(1, int(np.median(diffs[diffs > 0]) // MS_PER_MINUTE)) if (diffs > 0).any() else 1

    if parts & {"rth", "ib"}:
        rth_mask = (weekday < 5) & (minute >= RTH_START) & (minute < RTH_END)
        sessions = _groups(day, rth_mask)
        for k, rows in enumerate(sessions):
            if "rth" in parts:
                # Once the next session has started, this one is its pRTH: draw the box.
                if k < len(sessions) - 1:
                    out[rows, COL["rth_box_h"]] = float(np.nanmax(high[rows]))
                    out[rows, COL["rth_box_l"]] = float(np.nanmin(low[rows]))
                if k > 0:
                    prev = sessions[k - 1]
                    ph, pl = float(np.nanmax(high[prev])), float(np.nanmin(low[prev]))
                    _levels(out, rows, high, low, open_, epoch_ms, ph, pl,
                            ("prth_h", "prth_l", "rth_setup", "rth_third", "rth_touch_h", "rth_touch_l",
                             "rth_hit_h", "rth_hit_l"), tick)
            if "ib" in parts:
                ib_rows = rows[minute[rows] < IB_END]
                post = rows[minute[rows] >= IB_END]
                if not ib_rows.size or minute[ib_rows[0]] >= RTH_START + max(bar_min, 5):
                    continue  # the session's start is missing
                out[ib_rows, COL["ib_box_h"]] = np.maximum.accumulate(high[ib_rows])
                out[ib_rows, COL["ib_box_l"]] = np.minimum.accumulate(low[ib_rows])
                if not post.size:
                    continue
                ibh, ibl = float(np.nanmax(high[ib_rows])), float(np.nanmin(low[ib_rows]))
                mid, rng = (ibh + ibl) / 2, ibh - ibl
                last_close = float(close[ib_rows[-1]])
                out[post, COL["ib_h"]], out[post, COL["ib_l"]], out[post, COL["ib_mid"]] = ibh, ibl, mid
                out[post, COL["ib_side"]] = 1.0 if last_close > mid else -1.0 if last_close < mid else 0.0
                out[post, COL["ib_valid"]] = 1.0 if ibl < open_[post[0]] < ibh else 0.0
                up, dn = high[post] >= ibh + tick, low[post] <= ibl - tick
                first = None
                for col, hits, side in (("ib_hit_h", up, 1), ("ib_hit_l", dn, -1)):
                    if hits.any():
                        j = int(np.argmax(hits))
                        out[post[j:], COL[col]] = epoch_ms[post[j]]
                        if first is None or j < first[0]:
                            first = (j, side)
                if "retrace" in parts:
                    _retrace(out, rows, ib_rows, post, high, low, open_, close, epoch_ms, tick)
                if "targets" in parts and first is not None:
                    j, side = first
                    level = ibh if side == 1 else ibl
                    out[post[j:], COL["ib_ext_med"]] = level + side * IB_EXTENSION[0] * rng
                    out[post[j:], COL["ib_ext_p75"]] = level + side * IB_EXTENSION[1] * rng

    if "eth" in parts:
        in_eth = (minute >= ETH_START) | (minute < ETH_END)
        eth_day = day + (minute >= ETH_START)
        sessions = [g for g in _groups(eth_day, in_eth & (((eth_day + 3) % 7) < 5))]
        for k in range(len(sessions) - 1):  # every ETH day with a later one: its box (that day's pETH)
            out[sessions[k], COL["eth_box_h"]] = float(np.nanmax(high[sessions[k]]))
            out[sessions[k], COL["eth_box_l"]] = float(np.nanmin(low[sessions[k]]))
        for k in range(1, len(sessions)):
            prev, rows = sessions[k - 1], sessions[k]
            ph, pl = float(np.nanmax(high[prev])), float(np.nanmin(low[prev]))
            _levels(out, rows, high, low, open_, epoch_ms, ph, pl,
                    ("peth_h", "peth_l", "eth_setup", "eth_third", "eth_touch_h", "eth_touch_l",
                     "eth_hit_h", "eth_hit_l"), tick)
    return out


class Breaks(IndicatorBase):
    """IB, RTH and ETH breaks with the ES odds of each line getting hit."""

    spec = IndicatorSpec(
        id="breaks",
        name="Breaks",
        description=(
            "IB (first RTH hour), prior RTH and prior ETH highs / lows, where today opened "
            "and which lines got hit, with the ES 2016-2025 odds of each break."
        ),
        parameters={
            "show": {"type": "string", "default": DEFAULT_SHOW},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        # Monday needs Friday's RTH and ETH: a few calendar days of 1-minute bars.
        warmup_fn=lambda params: 6 * MINUTES_PER_DAY,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        merged = {**{k: v.get("default") for k, v in self.spec.parameters.items()}, **{k: v for k, v in (params or {}).items() if v is not None}}
        parts = parse_show(merged["show"])
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = breaks(
                epoch_ms, *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")), show=parts
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
