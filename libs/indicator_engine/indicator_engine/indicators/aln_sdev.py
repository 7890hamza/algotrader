"""ALN SDEV: the Net Change SDEV recipe for every ALN session in one indicator.

Each session has its own open and its own SDEV: the population standard deviation
(ddof=0) of the net change % (open to close) of that session's previous ``lookback``
complete sessions, drawn at open x (1 +/- k x SDEV / 100). This is the same math as
Net Change SDEV (AM, 5-9 AM Pacific) and CME Open SDEV (3-7 PM Pacific).

Sessions (Pacific unless noted):
  cme   3-7 PM, Sun-Thu (the CME Open SDEV window)
  asia  5-11 PM, Sun-Thu
  ldn   2-8 AM New York (11 PM-5 AM Pacific), Mon-Fri
  am    5-9 AM, Mon-Fri (the Net Change SDEV window)
  pm    9 AM-1 PM, Mon-Fri

Outputs: ``<session>_open`` and ``<session>_+0.5`` / ``_-0.5`` etc. for every multiplier;
only the multipliers in ``levels`` are filled.
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np

from ..core.bars import BarTensor
from ..core.spec import IndicatorSpec
from ..core.tensor import Tensor
from .base import IndicatorBase
from .session_sdev import (
    DEFAULT_LEVELS,
    MINUTES_PER_DAY,
    MULTIPLIERS,
    OUTPUTS as LEVEL_KEYS,
    parse_levels,
    session_levels,
    to_epoch_ms,
)

# key: (start, end, time zone, session days)
SESSIONS: dict[str, tuple[str, str, str, str]] = {
    "cme": ("15:00", "19:00", "America/Los_Angeles", "Sun-Thu"),
    "asia": ("17:00", "23:00", "America/Los_Angeles", "Sun-Thu"),
    "ldn": ("02:00", "08:00", "America/New_York", "Mon-Fri"),
    "am": ("05:00", "09:00", "America/Los_Angeles", "Mon-Fri"),
    "pm": ("09:00", "13:00", "America/Los_Angeles", "Mon-Fri"),
}
DEFAULT_SESSIONS = "cme, asia, ldn, am, pm"
OUTPUTS = [f"{s}_{k}" for s in SESSIONS for k in LEVEL_KEYS]


def parse_sessions(raw: object) -> list[str]:
    names = [p.strip().lower() for p in str(raw or "").replace(";", ",").split(",") if p.strip()]
    unknown = [n for n in names if n not in SESSIONS]
    if unknown:
        raise ValueError(f"Unknown sessions {unknown}; choose from {', '.join(SESSIONS)}")
    return names


def warmup_minutes(lookback: int) -> int:
    """Calendar minutes that hold ``lookback`` sessions plus weekends and holidays."""
    return math.ceil((lookback + 5) * 7 / 5) * MINUTES_PER_DAY


def _warmup(params: Dict) -> int:
    # The API passes the chart's bar length as "_bar_minutes"; without it assume 1-minute bars.
    bar = max(1, int(params.get("_bar_minutes") or 1))
    return math.ceil(warmup_minutes(int(params.get("lookback", 20))) / bar)


class AlnSDEV(IndicatorBase):
    """Every ALN session's open and +/- SDEV levels, each from its own history."""

    spec = IndicatorSpec(
        id="aln_sdev",
        name="ALN SDEV",
        description=(
            "Net Change SDEV for each ALN session (CME, Asia, London, AM, PM): the session "
            "open and +/- SDEV levels from that session's previous complete sessions."
        ),
        parameters={
            "sessions": {"type": "string", "default": DEFAULT_SESSIONS},
            "lookback": {"type": "int", "default": 20, "min": 2},
            "levels": {"type": "string", "default": DEFAULT_LEVELS},
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
        names = parse_sessions(merged["sessions"])
        lookback = int(merged["lookback"])
        levels = parse_levels(merged["levels"])
        idx = {}
        for field in ("open", "close"):
            if field not in data.fields:
                raise KeyError(f"Field not found: {field}")
            idx[field] = int(np.where(data.fields == field)[0][0])
        epoch_ms = to_epoch_ms(data.time)
        n_time, n_assets = data.data.shape[0], data.data.shape[1]
        width = len(LEVEL_KEYS)
        out = np.full((n_time, n_assets, len(OUTPUTS)), np.nan, dtype=np.float64)
        for a in range(n_assets):
            o, c = data.data[:, a, idx["open"]], data.data[:, a, idx["close"]]
            for name in names:
                start, end, tz, days = SESSIONS[name]
                col = list(SESSIONS).index(name) * width
                out[:, a, col:col + width] = session_levels(
                    epoch_ms, o, c, lookback=lookback, session_start=start, session_end=end,
                    time_zone=tz, session_days=days, levels=levels,
                )
        return Tensor(
            data=out,
            dims=("time", "asset", "output"),
            coords={"time": data.time, "asset": data.assets, "output": np.array(OUTPUTS, dtype=object)},
        )


__all__ = ["AlnSDEV", "MULTIPLIERS", "SESSIONS"]
