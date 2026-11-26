"""Bullish and bearish engulfing candles, bodies only (wicks ignored).

Bearish engulfing: the previous candle is green, the current one is red, the red body
covers the green body (open >= previous close, close <= previous open) and is bigger.
Bullish engulfing is the mirror. Equal prices count as covering.

Invalidation is body-based too: a bearish engulfing is broken when a later candle closes
above the engulfing candle's open; a bullish one when a later candle closes below it.

Outputs:

* ``signal``: +1 bullish / -1 bearish on the engulfing candle.
* ``body_top`` / ``body_bot``: the engulfing candle's body, on that candle.
* ``inval_bull`` / ``inval_bear``: the invalidation price of the latest bullish / bearish
  engulfing, from its candle until it is invalidated (drawn as a line).
* ``mae`` / ``mfe`` (points from the engulfing close, wicks count for these) measured until
  invalidation or ``window`` candles, ``outcome`` +1 when price ran one engulfing body in
  its favour before being invalidated, -1 when invalidated first, 0 while still open,
  and ``inval_at`` (epoch ms of the invalidating close), all on the engulfing candle.

Higher timeframe + 12-hour bias (the defaults; ``tf_minutes=0`` and ``bias="none"`` give the
old chart-timeframe behaviour):

* Engulfings are found on ``tf_minutes`` candles (60 = hourly) built from the chart's bars. Each
  one is placed on the chart bar where that hourly candle closes, so nothing shows early, and a
  still-forming hourly candle is never used.
* 12-hour candles run 6 PM-6 AM and 6 AM-6 PM New York (3 PM-3 AM / 3 AM-3 PM Pacific; the night
  one is the P12 window). Each is compared with the one before, by the wicks:
  HL = its low is above the previous low, LH = its high is below the previous high.
  Bias = up after an HL (without an LH), down after an LH (without an HL), else none. A 12-hour
  candle's bias applies only after it has closed (to the next 12 hours).
* With ``bias="12h"`` only engulfings in the bias direction are kept; the others go to
  ``against`` (their side) so the chart can hide them or show them faint.
* ``h12_high`` / ``h12_low``: the last closed 12-hour candle's high / low, on every chart bar of the
  next 12 hours, with ``h12_hi_tag`` (+1 HH, -1 LH, 0 same) / ``h12_lo_tag`` (+1 HL, -1 LL, 0 same)
  and ``bias`` (+1 / -1 / 0).
  Tested on ES 2022-2026 hourly: 65% of all engulfings ran one body before failing, 65% of those
  with the bias and 64% against it, so the bias cuts the count by about 3/4 without changing odds.

No-wick (marubozu) candles: a green candle that opened at its low or a red candle that
opened at its high, with a body of at least ``maru_min_body`` points. ``maru_side``
(+1 green / -1 red) and ``maru_price`` (the open, the no-wick end) sit on that candle and
``maru_back_at`` is the epoch ms of the first later candle that traded back to it.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import to_epoch_ms

from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
HOUR_MS = 3_600_000

OUTPUTS = [
    "signal",
    "body_top",
    "body_bot",
    "inval_bull",
    "inval_bear",
    "mae",
    "mfe",
    "outcome",
    "inval_at",
    "maru_side",
    "maru_price",
    "maru_back_at",
    "h12_high",
    "h12_low",
    "h12_hi_tag",
    "h12_lo_tag",
    "bias",
    "against",
]
COL = {name: i for i, name in enumerate(OUTPUTS)}


def engulfing(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    window: int = 24,
    maru_min_body: float = 1.0,
) -> np.ndarray:
    """Return an array (time, len(OUTPUTS)); see the module docstring."""
    n = len(open_)
    out = np.full((n, len(OUTPUTS)), np.nan, dtype=np.float64)
    if n < 2:
        return out
    o, h, lo, c = (np.asarray(a, dtype=np.float64) for a in (open_, high, low, close))
    po, pc = o[:-1], c[:-1]
    co, cc = o[1:], c[1:]
    with np.errstate(invalid="ignore"):
        bear = (pc > po) & (cc < co) & (co >= pc) & (cc <= po) & ((co - cc) > (pc - po))
        bull = (pc < po) & (cc > co) & (co <= pc) & (cc >= po) & ((cc - co) > (po - pc))
    for i in np.flatnonzero(bear | bull) + 1:
        side = 1 if bull[i - 1] else -1
        body = abs(c[i] - o[i])
        out[i, COL["signal"]] = side
        out[i, COL["body_top"]] = max(o[i], c[i])
        out[i, COL["body_bot"]] = min(o[i], c[i])
        later = np.arange(i + 1, min(n, i + 1 + window))
        broken = (c[later] < o[i]) if side == 1 else (c[later] > o[i])
        j = int(later[np.argmax(broken)]) if broken.any() else None
        seg = later if j is None else np.arange(i + 1, j + 1)
        line_end = (j + 1) if j is not None else min(n, i + 1 + window)
        out[i:line_end, COL["inval_bull" if side == 1 else "inval_bear"]] = o[i]
        if seg.size:
            fav = (h[seg] - c[i]) if side == 1 else (c[i] - lo[seg])
            adv = (c[i] - lo[seg]) if side == 1 else (h[seg] - c[i])
            out[i, COL["mfe"]] = max(float(fav.max()), 0.0)
            out[i, COL["mae"]] = max(float(adv.max()), 0.0)
            reached = np.flatnonzero(fav >= body)
            if reached.size and (j is None or seg[reached[0]] <= j):
                out[i, COL["outcome"]] = 1
            elif j is not None:
                out[i, COL["outcome"]] = -1
            else:
                out[i, COL["outcome"]] = 0
        else:
            out[i, COL["mae"]] = 0.0
            out[i, COL["mfe"]] = 0.0
            out[i, COL["outcome"]] = 0
        if j is not None:
            out[i, COL["inval_at"]] = float(epoch_ms[j])
    _marubozu(out, epoch_ms, o, h, lo, c, maru_min_body)
    return out


def _first_back(start: int, price: float, side: int, h: np.ndarray, lo: np.ndarray) -> int | None:
    """First index >= start that trades back to ``price`` (searched in growing chunks)."""
    n, size = len(h), 16
    while start < n:
        stop = min(n, start + size)
        hit = (lo[start:stop] <= price) if side == 1 else (h[start:stop] >= price)
        if hit.any():
            return start + int(np.argmax(hit))
        start, size = stop, size * 4
    return None


def _marubozu(out, epoch_ms, o, h, lo, c, min_body: float) -> None:
    with np.errstate(invalid="ignore"):
        big = np.abs(c - o) >= min_body
        green = big & (c > o) & (o == lo)
        red = big & (c < o) & (o == h)
    for i in np.flatnonzero(green | red):
        side = 1 if green[i] else -1
        out[i, COL["maru_side"]] = side
        out[i, COL["maru_price"]] = o[i]
        k = _first_back(i + 1, o[i], side, h, lo)
        if k is not None:
            out[i, COL["maru_back_at"]] = float(epoch_ms[k])


def _ny_offset_ms(epoch_ms: np.ndarray) -> np.ndarray:
    """New York's UTC offset (ms) for each time, looked up once per hour."""
    from datetime import datetime, timezone

    hours = (epoch_ms // HOUR_MS).astype(np.int64)
    uniq, inv = np.unique(hours, return_inverse=True)
    offs = np.array(
        [datetime.fromtimestamp(int(hh) * 3600, tz=timezone.utc).astimezone(NEW_YORK).utcoffset().total_seconds() * 1000 for hh in uniq],
        dtype=np.int64,
    )
    return offs[inv]


def _buckets(keys: np.ndarray):
    """Start index of each run of equal keys, and its last index."""
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    ends = np.r_[starts[1:] - 1, len(keys) - 1]
    return starts, ends


def _bar_ms(epoch_ms: np.ndarray) -> int:
    d = np.diff(epoch_ms)
    d = d[d > 0]
    return int(np.median(d)) if d.size else 60_000


def twelve_hour_bias(epoch_ms, high, low):
    """Per chart bar: last closed 12-hour candle's high / low, HH-LH / HL-LL tags and the bias."""
    n = len(epoch_ms)
    res = {k: np.full(n, np.nan) for k in ("h12_high", "h12_low", "h12_hi_tag", "h12_lo_tag", "bias")}
    if n == 0:
        return res
    local = epoch_ms + _ny_offset_ms(epoch_ms)
    key = (local - 6 * HOUR_MS) // (12 * HOUR_MS)  # 6 AM / 6 PM New York boundaries
    starts, ends = _buckets(key)
    bar = _bar_ms(epoch_ms)
    prev = None  # (high, low) of the 12-hour candle before
    closed = None  # values that apply after the latest closed candle
    for b, (a, z) in enumerate(zip(starts, ends)):
        if closed is not None:
            for name, v in closed.items():
                res[name][a : z + 1] = v
        bucket_end = (int(key[a]) + 1) * 12 * HOUR_MS + 6 * HOUR_MS  # in local ms
        complete = b < len(starts) - 1 or local[z] + bar >= bucket_end
        if not complete:
            break
        hi, lo = float(np.nanmax(high[a : z + 1])), float(np.nanmin(low[a : z + 1]))
        if prev is not None:
            hi_tag = 1.0 if hi > prev[0] else (-1.0 if hi < prev[0] else 0.0)
            lo_tag = 1.0 if lo > prev[1] else (-1.0 if lo < prev[1] else 0.0)
            hl, lh = lo_tag == 1.0, hi_tag == -1.0
            bias = 1.0 if (hl and not lh) else (-1.0 if (lh and not hl) else 0.0)
            closed = {"h12_high": hi, "h12_low": lo, "h12_hi_tag": hi_tag, "h12_lo_tag": lo_tag, "bias": bias}
        prev = (hi, lo)
    return res


def engulfing_htf(epoch_ms, open_, high, low, close, *, window=24, maru_min_body=1.0, tf_minutes=60, bias="12h", show_against=False):
    """Engulfings on ``tf_minutes`` candles, placed on the chart bar where each closes, plus the 12-hour bias."""
    epoch_ms = np.asarray(epoch_ms, dtype=np.int64)
    o, h, lo, c = (np.asarray(a, dtype=np.float64) for a in (open_, high, low, close))
    n = len(o)
    bar = _bar_ms(epoch_ms) if n > 1 else 60_000
    if tf_minutes and tf_minutes * 60_000 > bar:
        tf = tf_minutes * 60_000
        local = epoch_ms + _ny_offset_ms(epoch_ms)
        starts, ends = _buckets(local // tf)
        if n and local[ends[-1]] + bar < (local[ends[-1]] // tf + 1) * tf:
            starts, ends = starts[:-1], ends[:-1]  # the hourly candle still forming is not a candle yet
        ho = o[starts]
        hh = np.array([np.nanmax(h[a : z + 1]) for a, z in zip(starts, ends)])
        hl = np.array([np.nanmin(lo[a : z + 1]) for a, z in zip(starts, ends)])
        hc = c[ends]
        h_out = engulfing(epoch_ms[ends], ho, hh, hl, hc, window=window, maru_min_body=maru_min_body)
        out = np.full((n, len(OUTPUTS)), np.nan)
        point_cols = [COL[k] for k in ("signal", "body_top", "body_bot", "mae", "mfe", "outcome", "inval_at", "maru_side", "maru_price", "maru_back_at")]
        out[ends[:, None], point_cols] = h_out[:, point_cols]
        # invalidation lines: from the bar the hourly candle closed on, over the hours it stays valid
        for col in (COL["inval_bull"], COL["inval_bear"]):
            for k in np.flatnonzero(~np.isnan(h_out[:, col])):
                first = ends[k] if (k == 0 or h_out[k - 1, col] != h_out[k, col]) else starts[k]
                out[first : ends[k] + 1, col] = h_out[k, col]
    else:
        out = engulfing(epoch_ms, o, h, lo, c, window=window, maru_min_body=maru_min_body)
    for name, values in twelve_hour_bias(epoch_ms, h, lo).items():
        out[:, COL[name]] = values
    if bias == "12h":
        sig = out[:, COL["signal"]]
        against = ~np.isnan(sig) & (sig != out[:, COL["bias"]])
        out[against, COL["against"]] = sig[against]
        if not show_against:
            for name in ("signal", "body_top", "body_bot", "mae", "mfe", "outcome", "inval_at"):
                out[against, COL[name]] = np.nan
            # and their invalidation lines
            for i in np.flatnonzero(against):
                col = COL["inval_bull"] if sig[i] == 1 else COL["inval_bear"]
                price = out[i, col]
                j = i
                while j < n and out[j, col] == price:
                    out[j, col] = np.nan
                    j += 1
    return out


class Engulfing(IndicatorBase):
    """Body-to-body engulfing candles with body-close invalidation and MAE / MFE."""

    spec = IndicatorSpec(
        id="engulfing",
        name="Engulfing Candles",
        description=(
            "Bullish and bearish engulfing candles, bodies only: the body covers the previous "
            "opposite body and is bigger. Invalidated by a close beyond the engulfing open. "
            "By default found on 60-minute candles and kept only in the direction of the 12-hour "
            "bias (HL = up, LH = down, by the wicks). "
            "Also marks no-wick (marubozu) candle opens until price comes back to them."
        ),
        parameters={
            "window": {"type": "int", "default": 24, "min": 2},
            "maru_min_body": {"type": "float", "default": 1.0, "min": 0},
            "tf_minutes": {"type": "int", "default": 60, "min": 0},
            "bias": {"type": "string", "default": "12h"},  # "12h" or "none"
            "show_against": {"type": "int", "default": 0, "min": 0, "max": 1},  # 1 = keep the ones against the bias
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=lambda params: 2,  # the chart loads days of bars; 12-hour bias needs 2 closed 12h candles
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        window = int(params.get("window") or self.spec.parameters["window"]["default"])
        min_body = params.get("maru_min_body")
        min_body = 1.0 if min_body is None else float(min_body)
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = engulfing_htf(
                epoch_ms,
                *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")),
                window=window,
                maru_min_body=min_body,
                tf_minutes=int(params.get("tf_minutes", 60) or 0),
                bias=str(params.get("bias") or "12h"),
                show_against=bool(int(params.get("show_against") or 0)),
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
