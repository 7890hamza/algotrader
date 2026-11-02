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
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import to_epoch_ms

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
    return out


class Engulfing(IndicatorBase):
    """Body-to-body engulfing candles with body-close invalidation and MAE / MFE."""

    spec = IndicatorSpec(
        id="engulfing",
        name="Engulfing Candles",
        description=(
            "Bullish and bearish engulfing candles, bodies only: the body covers the previous "
            "opposite body and is bigger. Invalidated by a close beyond the engulfing open."
        ),
        parameters={"window": {"type": "int", "default": 24, "min": 2}},
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        warmup_fn=lambda params: 2,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        window = int(params.get("window") or self.spec.parameters["window"]["default"])
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            out[:, a, :] = engulfing(
                epoch_ms,
                *(data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")),
                window=window,
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
