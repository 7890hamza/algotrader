"""ALN TBR: the AM TBR "open fade" applied to each ALN session.

For each session (New York time): the open is the first bar, 1 SDEV is the sample SDEV
(ddof=1) of the previous 20 complete sessions' % net change (open to the last bar), and
lines sit at open +/- 0.25 SDEV. After the first touch, zones appear (median to 90th
percentile, ``*_mid`` = 75th percentile, in SDEV from the open), from the ES 2016-2025
study: ``stretch`` (push past the line on sessions that came back), ``runaway`` (sessions
that never came back) and ``follow`` (past the open on the other side after coming back).
``<s>_revert_at`` is the epoch ms of the first trade back at the open after the touch.

Sessions may cross midnight (Asia 20:00-02:00). A session is complete when it has at
least 83% of its minutes, its first bar within 5 minutes of the start and its last bar
within 5 minutes of the end.
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

# name: (start minute New York, length in minutes)
SESSIONS: dict[str, tuple[int, int]] = {
    "asia": (20 * 60, 360),
    "ldn": (2 * 60, 360),
    "am": (8 * 60, 240),
    "pm": (12 * 60, 240),
    "ny": (8 * 60, 480),
}
ZONES = ("stretch", "runaway", "follow")
# (median, p75, p90) in SDEV, ES 2016-2025, 1-minute AMP data.
ZONE_STATS: dict[str, dict[str, tuple[float, float, float]]] = {
    "asia": {
        "stretch": (0.409, 0.598, 0.907),
        "runaway": (1.256, 1.785, 2.457),
        "follow": (0.476, 0.972, 1.752),
    },
    "ldn": {
        "stretch": (0.397, 0.608, 0.901),
        "runaway": (1.317, 1.914, 2.620),
        "follow": (0.533, 1.023, 1.764),
    },
    "am": {
        "stretch": (0.408, 0.595, 0.903),
        "runaway": (1.241, 1.725, 2.610),
        "follow": (0.509, 1.045, 1.686),
    },
    "pm": {
        "stretch": (0.401, 0.588, 0.903),
        "runaway": (1.180, 1.755, 2.507),
        "follow": (0.478, 0.965, 1.673),
    },
    "ny": {
        "stretch": (0.399, 0.579, 0.843),
        "runaway": (1.264, 1.831, 2.491),
        "follow": (0.511, 0.995, 1.648),
    },
}
FIELDS = ["open", "up", "dn", "revert_at"] + [
    f"{z}_{e}" for z in ZONES for e in ("near", "far", "mid")
]
OUTPUTS = [f"{s}_{f}" for s in SESSIONS for f in FIELDS]
COL = {name: i for i, name in enumerate(OUTPUTS)}
NEW_YORK = ZoneInfo("America/New_York")
LEVEL = 0.25
LOOKBACK = 20


def session_fade(
    epoch_ms: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    name: str,
    *,
    lookback: int = LOOKBACK,
    ddof: int = 1,
) -> np.ndarray:
    """Return (time, len(FIELDS)) for one session; see the module docstring."""
    start, length = SESSIONS[name]
    n = len(epoch_ms)
    out = np.full((n, len(FIELDS)), np.nan, dtype=np.float64)
    if n == 0:
        return out
    local = _local_ms(np.asarray(epoch_ms, dtype=np.int64), NEW_YORK)
    minute = (local % MS_PER_DAY) // MS_PER_MINUTE
    day = local // MS_PER_DAY
    offset = (minute - start) % MINUTES_PER_DAY
    inside = np.flatnonzero(
        (offset < length) & np.isfinite(open_) & np.isfinite(high) & np.isfinite(low)
    )
    if inside.size == 0:
        return out
    sid = day[inside] - (minute[inside] < start)
    starts = np.flatnonzero(np.r_[True, sid[1:] != sid[:-1]])
    ends = np.r_[starts[1:], inside.size]
    diffs = np.diff(epoch_ms[inside])
    bar_minutes = max(1, int(np.median(diffs) // MS_PER_MINUTE)) if diffs.size else 1
    edge = max(5, bar_minutes)
    need = 0.83 * length / bar_minutes

    sessions = []  # (rows, complete, net % change)
    for a, b in zip(starts, ends):
        rows = inside[a:b]
        off = offset[rows]
        complete = (b - a) >= need and off[0] < edge and off[-1] >= length - edge
        chg = (close[rows[-1]] - open_[rows[0]]) / open_[rows[0]] * 100 if complete else np.nan
        sessions.append((rows, complete, chg))

    history: list[float] = []
    stats = ZONE_STATS[name]
    for rows, complete, chg in sessions:
        if len(history) >= lookback and offset[rows[0]] < edge:
            sd = float(np.std(history[-lookback:], ddof=ddof))
            o = float(open_[rows[0]])
            pts = o * sd / 100
            up, dn = o + LEVEL * pts, o - LEVEL * pts
            out[rows, 0], out[rows, 1], out[rows, 2] = o, up, dn
            hh, ll = high[rows], low[rows]
            hits = np.flatnonzero((hh >= up) | (ll <= dn))
            if hits.size:
                k = int(hits[0])
                both = hh[k] >= up and ll[k] <= dn
                bar_open = open_[rows[k]]
                side = (
                    1
                    if hh[k] >= up and (not both or abs(bar_open - up) <= abs(bar_open - dn))
                    else -1
                )
                back = (ll[k + 1 :] <= o) if side == 1 else (hh[k + 1 :] >= o)
                if back.any():
                    j = k + 1 + int(np.argmax(back))
                    out[rows[j:], 3] = epoch_ms[rows[j]]
                after = rows[k:]
                for z_i, zone in enumerate(ZONES):
                    med, p75, p90 = stats[zone]
                    direction = -side if zone == "follow" else side
                    col = 4 + 3 * z_i
                    out[after, col] = o + direction * med * pts
                    out[after, col + 1] = o + direction * p90 * pts
                    out[after, col + 2] = o + direction * p75 * pts
        if complete:
            history.append(chg)
    return out


def parse_sessions(raw: str) -> list[str]:
    names = [part.strip().lower() for part in str(raw).replace(";", ",").split(",") if part.strip()]
    unknown = [name for name in names if name not in SESSIONS]
    if unknown:
        raise ValueError(f"Unknown sessions {unknown}; choose from {', '.join(SESSIONS)}")
    return names


class AlnTBR(IndicatorBase):
    """Open fade (+/- 0.25 SDEV back to the open) for the Asia, London and AM sessions."""

    spec = IndicatorSpec(
        id="aln_tbr",
        name="ALN TBR",
        description=(
            "The AM TBR open fade for each ALN session: session open, +/- 0.25 SDEV, a diamond "
            "where price came back to the open, and stretch / no-return / follow-through zones."
        ),
        parameters={
            "sessions": {"type": "string", "default": "asia, ldn, am"},
            "lookback": {"type": "int", "default": LOOKBACK, "min": 2},
        },
        outputs=OUTPUTS,
        required_fields=["open", "high", "low", "close"],
        supports_update=False,
        supports_vectorized=False,
        # 20 complete sessions plus weekends and holidays, in 1-minute bars.
        warmup_fn=lambda params: 35 * MINUTES_PER_DAY,
        requires_full_warmup=False,
        sparse_outputs=True,
    )

    def batch(self, data: BarTensor, params: Dict) -> Tensor:
        defaults = {k: v["default"] for k, v in self.spec.parameters.items()}
        merged = {**defaults, **{k: v for k, v in params.items() if v is not None}}
        names = parse_sessions(merged["sessions"])
        idx = {}
        for field in ("open", "high", "low", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            series = [data.data[:, a, idx[f]] for f in ("open", "high", "low", "close")]
            for name in names:
                first = COL[f"{name}_open"]
                out[:, a, first : first + len(FIELDS)] = session_fade(
                    epoch_ms, *series, name, lookback=int(merged["lookback"])
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
