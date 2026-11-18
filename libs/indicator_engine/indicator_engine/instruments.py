"""Which instrument an indicator is running on, and what that changes.

Every stat table in this engine was measured on one of two index futures:

* ``ES`` - S&P 500 (E-mini). MES (micro) and Hyperliquid trade.xyz ``SP500`` track the same
  index.
* ``NQ`` - Nasdaq-100 (E-mini). MNQ (micro) and Hyperliquid trade.xyz ``XYZ100`` track the same
  index.

The stats are in SDEV units or % of price, so a micro uses its big contract's table unchanged; only
the money per point differs. What each instrument changes:

* ``family``      which table to read ("ES" or "NQ")
* ``tick``        the smallest price step, so "1 tick past a level" is right for every market.
                  CME: fixed (0.25). Hyperliquid perps: at most 5 significant figures, so the
                  step depends on price (SP500 near 6,800 -> 0.1; XYZ100 near 25,000 -> 1).
* ``point_value`` USD per 1.0 of price for one contract / unit (ES 50, MES 5, NQ 20, MNQ 2, perps 1)
* ``venue``       "CME" or "HYPERLIQUID". Hyperliquid trades 24/7, but every stat counts CME
                  trading time only, so session math there uses only the bars when CME Globex is
                  open (``cme_open``): no Saturday "sessions", no daily-break hour.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from zoneinfo import ZoneInfo

FAMILIES = ("ES", "NQ")
CME, HYPERLIQUID = "CME", "HYPERLIQUID"
CHICAGO = ZoneInfo("America/Chicago")
MS_PER_MINUTE = 60_000
MS_PER_DAY = 86_400_000


@dataclass(frozen=True)
class Instrument:
    symbol: str
    family: str
    venue: str
    tick_size: float | None  # None: the step depends on price (Hyperliquid)
    point_value: float
    name: str
    known: bool = True

    def tick(self, price: float | None = None) -> float:
        """Smallest price step at ``price`` (fixed for CME contracts)."""
        if self.tick_size:
            return self.tick_size
        if price is None or not math.isfinite(price) or price <= 0:
            return 1.0 if self.family == "NQ" else 0.1
        return float(10 ** (math.floor(math.log10(price)) - 4))  # 5 significant figures

    def tick_for(self, prices: np.ndarray) -> float:
        """One step for a whole series: the step at the series' median price."""
        if self.tick_size:
            return self.tick_size
        finite = np.asarray(prices, dtype=np.float64)
        finite = finite[np.isfinite(finite) & (finite > 0)]
        return self.tick(float(np.median(finite)) if finite.size else None)

    @property
    def trades_around_the_clock(self) -> bool:
        return self.venue == HYPERLIQUID


INSTRUMENTS: dict[str, Instrument] = {
    "ES": Instrument("ES", "ES", CME, 0.25, 50.0, "E-mini S&P 500"),
    "MES": Instrument("MES", "ES", CME, 0.25, 5.0, "Micro E-mini S&P 500"),
    "NQ": Instrument("NQ", "NQ", CME, 0.25, 20.0, "E-mini Nasdaq-100"),
    "MNQ": Instrument("MNQ", "NQ", CME, 0.25, 2.0, "Micro E-mini Nasdaq-100"),
    "SP500": Instrument("SP500", "ES", HYPERLIQUID, None, 1.0, "trade.xyz S&P 500 perp"),
    "XYZ100": Instrument("XYZ100", "NQ", HYPERLIQUID, None, 1.0, "trade.xyz Nasdaq-100 perp"),
}

# Broker / platform spellings of the same markets.
ALIASES: dict[str, str] = {
    "EP": "ES",
    "ENQ": "NQ",
    "MES": "MES",
    "MNQ": "MNQ",
    "US500": "SP500",
    "SPX": "SP500",
    "SPX500": "SP500",
    "SP500": "SP500",
    "US100": "XYZ100",
    "USTEC": "XYZ100",
    "NAS100": "XYZ100",
    "NDX": "XYZ100",
    "XYZ100": "XYZ100",
}
_MONTH = re.compile(r"^(MES|MNQ|ES|NQ|EP|ENQ)[FGHJKMNQUVXZ]\d{1,4}$")


def root_symbol(asset: object) -> str:
    """Root of a chart / broker symbol.

    "MNQZ26" -> "MNQ", "@EP" -> "ES", "/ES" -> "ES", "ES 12-26" -> "ES", "xyz:SP500" -> "SP500".
    """
    s = str(asset or "").upper().strip()
    if ":" in s:  # Hyperliquid builder dex coins: "xyz:SP500"
        s = s.split(":", 1)[1]
    s = s.lstrip("@/")
    s = re.split(r"[\s._-]", s)[0] if s else s
    if s in INSTRUMENTS or s in ALIASES:
        return ALIASES.get(s, s)
    m = _MONTH.match(s)
    if m:
        return ALIASES.get(m.group(1), m.group(1))
    if s.endswith("1!"):  # TradingView continuous
        return root_symbol(s[:-2])
    return s


def instrument_for(asset: object) -> Instrument:
    """The instrument for a chart symbol. Unknown symbols get the ES table and a 0.25 tick, the
    behaviour every indicator had before, flagged ``known=False``."""
    root = root_symbol(asset)
    if root in INSTRUMENTS:
        return INSTRUMENTS[root]
    family = "NQ" if "NQ" in root or "NAS" in root or "100" in root else "ES"
    return Instrument(root or "?", family, CME, 0.25, 1.0, root or "unknown", known=False)


def family_for(asset: object, choice: object = "auto") -> str:
    """ "ES" / "NQ" for ``asset``; ``choice`` other than "auto" forces one."""
    forced = str(choice or "auto").strip().upper()
    if forced in FAMILIES:
        return forced
    return instrument_for(asset).family


def cme_open(epoch_ms: np.ndarray) -> np.ndarray:
    """True for minutes when CME Globex equity futures trade: Sunday 5 PM to Friday 4 PM Central,
    without the 4-5 PM Central daily break."""
    t = np.asarray(epoch_ms, dtype=np.int64)
    if t.size == 0:
        return np.zeros(0, dtype=bool)
    # Chicago offset per bar: look it up once per distinct UTC day (DST changes at 2 AM local).
    days = t // MS_PER_DAY
    uniq, inv = np.unique(days, return_inverse=True)
    offsets = np.empty(uniq.size, dtype=np.int64)
    for i, d in enumerate(uniq):
        noon = datetime.fromtimestamp(int(d) * 86_400 + 43_200, tz=timezone.utc)
        offsets[i] = int(
            (noon.astimezone(CHICAGO).utcoffset() or timedelta(0)).total_seconds() * 1000
        )
    local = t + offsets[inv]
    # Near a DST switch the noon offset can be an hour off for a few early-morning bars: those are
    # never at the Sunday open, Friday close or daily break, so the answer does not change.
    wd = ((local // MS_PER_DAY) + 3) % 7  # Monday == 0
    hour = (local % MS_PER_DAY) // (60 * MS_PER_MINUTE)
    closed = (
        (wd == 5)
        | ((wd == 6) & (hour < 17))
        | ((wd == 4) & (hour >= 16))
        | ((wd < 4) & (hour == 16))
    )
    return ~closed


def session_rows(asset: object, epoch_ms: np.ndarray) -> np.ndarray | None:
    """Rows an indicator should use for ``asset``: None means all of them (CME markets); for a
    24/7 market, only the rows when CME is open, so its sessions match the futures' sessions."""
    if not instrument_for(asset).trades_around_the_clock:
        return None
    return np.flatnonzero(cme_open(epoch_ms))


def run_on_session_rows(
    asset: object, epoch_ms: np.ndarray, columns: list[np.ndarray], width: int, fn
):
    """Call ``fn(epoch_ms, *columns) -> (time, width)`` on the rows CME trades for ``asset`` and
    return a full-length array, NaN on rows that were left out."""
    rows = session_rows(asset, epoch_ms)
    if rows is None:
        return fn(epoch_ms, *columns)
    out = np.full((len(epoch_ms), width), np.nan, dtype=np.float64)
    if rows.size:
        out[rows] = fn(np.asarray(epoch_ms)[rows], *(np.asarray(c)[rows] for c in columns))
    return out


__all__ = [
    "Instrument",
    "INSTRUMENTS",
    "FAMILIES",
    "CME",
    "HYPERLIQUID",
    "instrument_for",
    "family_for",
    "root_symbol",
    "cme_open",
    "session_rows",
    "run_on_session_rows",
]
