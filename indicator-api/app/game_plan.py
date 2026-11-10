"""Game Plan: every stat target for one CME day, with what got hit, when, and what carried over.

The chart's Game Plan panel reads this. One CME day runs 3 PM - 2 PM Pacific (6 PM - 5 PM New
York). Targets come from the indicators already on the chart, with their ES 2016-2025 odds:

* pETH / pRTH  yesterday's full-session and RTH high / low (Breaks)
* IB           IB high / low from 7:30 AM, and the 0.62x / 1.18x extensions after the first break
* Week         last week's high / low
* SDEV         each ALN session's open and its +/-0.5 and +/-1 SDEV bands
* Hour         each hour's prior-hour high / low, and "back to the open" after a sweep
* AMTB         AM TBR: TBR open +/-0.25 SDEV; after the touch, back to the open, the stretch and
               no-return zones; after the return, the follow-through
* TBR          the same open fade for the CME, Asia, London, NY PM and NY sessions (ALN TBR)
* MTF SDEV     the day's, week's and month's +/-0.5 / 1 / 1.5 SDEV bands
* Opens        back to the day (Globex) open from 6:30 and to the RTH open from 7:30 (Current Day OHL)
* ALN          Asia and London highs / lows, with the London break odds for the pattern (ALN Sessions)
* IB retrace   the 40% ("In") and 60% lines of the current leg and its start (Breaks)

TBR and IB retrace lines belong to their own session: they don't carry over.

Carry-over: a target its own session misses stays open for the rest of the day (``origUntil``
is where its odds stop applying, ``until`` the end of the day). Whatever the whole previous day
missed is added again as an untouched level (``fromDay``). A hit is a trade 1 tick past the
level (a touch for "back to the open").
"""

from __future__ import annotations

import statistics as st
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
from indicator_engine.indicators.aln_sessions import _pattern
from indicator_engine.indicators.aln_tbr import F as TF
from indicator_engine.indicators.aln_tbr import session_fade
from indicator_engine.indicators.am_tbr import COL as AC
from indicator_engine.indicators.am_tbr import am_tbr
from indicator_engine.indicators.breaks import COL as BC
from indicator_engine.indicators.breaks import breaks
from indicator_engine.indicators.hour_stats import COL as HC
from indicator_engine.indicators.hour_stats import hour_stats
from indicator_engine.indicators.mtf_sdev import COL as MC
from indicator_engine.indicators.mtf_sdev import mtf_sdev
from zoneinfo import ZoneInfo

from app.ui_metadata import ALN_STATS, BREAK_RATES, HOUR_RATES, HOUR_SLICES, TBR_RATES

PT = ZoneInfo("America/Los_Angeles")
NY = ZoneInfo("America/New_York")
TICK = 0.25
HOUR_MS = 3_600_000

# How often each ALN session reaches its own SDEV band, ES 2016-2025 (1-minute data), as
# [up %, down %]. Population SDEV of the previous 20 sessions' net change %.
SDEV_HITS: dict[str, dict[str, list[float]]] = {
    "asia": {"0.5": [56.1, 54.7], "1": [29.1, 27.0]},
    "ldn": {"0.5": [59.1, 56.6], "1": [30.9, 30.8]},
    "am": {"0.5": [56.0, 58.1], "1": [28.6, 31.2]},
    "pm": {"0.5": [57.8, 53.3], "1": [28.0, 29.5]},
    "cme": {"0.5": [52.6, 52.1], "1": [26.3, 26.9]},  # CME Open SDEV, 3-7 PM
}

# Open fade (AM TBR / ALN TBR), ES 2016-2025 1-minute: how often each +/-0.25 line is reached
# [up, down]; of touched sessions, the share reaching each zone line and how many of those
# still came back to the open; the share coming back overall.
TBR_ODDS: dict[str, dict] = {
    "cme": {"line": [75.7, 74.7], "back": 73.3, "s_med": 60.1, "s_p75": 38.4, "s_p90": 22.9,
            "r_med": [18.1, 26.2], "r_p75": [7.8, 14.6], "not_r": 83.8},
    "asia": {"line": [75.4, 73.7], "back": 75.6, "s_med": 61.2, "s_p75": 41.1, "s_p90": 24.7,
             "r_med": [15.4, 21.0], "r_p75": [6.8, 10.5], "not_r": 85.6},
    "ldn": {"line": [78.7, 76.4], "back": 77.4, "s_med": 60.5, "s_p75": 40.3, "s_p90": 25.4,
            "r_med": [13.7, 17.3], "r_p75": [6.2, 9.3], "not_r": 87.0},
    "am": {"line": [76.0, 77.1], "back": 75.8, "s_med": 60.6, "s_p75": 40.4, "s_p90": 24.9,
           "r_med": [15.0, 18.7], "r_p75": [6.9, 13.1], "not_r": 85.8},
    "pm": {"line": [78.9, 73.8], "back": 75.0, "s_med": 61.5, "s_p75": 40.6, "s_p90": 24.5,
           "r_med": [15.8, 20.4], "r_p75": [6.9, 9.2], "not_r": 85.0},
    "ny": {"line": [76.2, 76.3], "back": 74.4, "s_med": 62.1, "s_p75": 42.3, "s_p90": 27.7,
           "r_med": [15.1, 14.6], "r_p75": [7.0, 8.4], "not_r": 85.1},
}
# Hour stats: how often each New York hour (open inside the prior hour's range) trades 1 tick past
# the prior-hour [high, low]. ES 2016-2025 1-minute.
HOUR_SWEEP: dict[int, list[float]] = {
    0: [40.8, 40.3], 1: [52.8, 48.8], 2: [54.9, 50.6], 3: [58.6, 55.6], 4: [42.4, 38.5],
    5: [42.4, 38.2], 6: [47.6, 42.9], 7: [52.2, 42.8], 8: [54.4, 53.9], 9: [64.7, 61.6],
    10: [52.2, 48.8], 11: [44.3, 38.2], 12: [44.5, 39.5], 13: [49.6, 42.3], 14: [52.7, 46.8],
    15: [58.7, 50.0], 16: [28.9, 24.5], 19: [38.4, 36.3], 20: [52.4, 50.8], 21: [43.6, 39.5],
    22: [38.5, 34.7], 23: [40.0, 34.9],
}
# key: (name, start hour PT, end hour PT, day offset, color)
TBR_SESSIONS: dict[str, tuple[str, int, int, int, str]] = {
    "cme": ("CME", 15, 17, -1, "#A78BFA"),
    "asia": ("Asia", 17, 23, -1, "#E0574A"),
    "ldn": ("London", 23, 29, -1, "#5B7CFA"),
    "am": ("AMTB", 5, 9, 0, "#3FB950"),
    "pm": ("NY PM", 9, 13, 0, "#26A69A"),
    "ny": ("NY", 5, 13, 0, "#2E9E57"),
}
# MTF SDEV: how often the day / week / month reaches each band, [up %, down %].
MTF_HITS: dict[str, dict[str, list[float]]] = {
    "d": {"0.5": [59.8, 55.1], "1": [29.8, 29.7], "1.5": [14.5, 16.6]},
    "w": {"0.5": [58.8, 52.1], "1": [27.7, 28.7], "1.5": [12.1, 16.0]},
    "m": {"0.5": [70.9, 55.6], "1": [39.3, 30.8], "1.5": [21.4, 17.9]},
}
MTF_NAMES = {"d": "Day", "w": "Week", "m": "Month"}
# Back to the open: the day (Globex) open from 6:30 to 1 PM, the RTH open from 7:30 to 1 PM.
OPEN_BACK = {"day": 58.4, "rth": 59.7}
ALN_TEXT = {1: "London took both Asia's high and low", 2: "London stayed inside Asia's range",
            3: "London took Asia's high only", 4: "London took Asia's low only"}

# key: (name, start hour PT, end hour PT, start day offset from the trading day)
SESSIONS: dict[str, tuple[str, int, int, int]] = {
    "asia": ("Asia", 15, 23, -1),
    "ldn": ("London", 23, 29, -1),
    "am": ("NY AM", 5, 9, 0),
    "pm": ("NY PM", 9, 14, 0),
}
# SDEV windows (the ALN SDEV indicator's sessions; NY PM's band session ends at 1 PM).
SDEV_WINDOWS: dict[str, tuple[int, int, int]] = {
    "asia": (17, 23, -1),
    "ldn": (23, 29, -1),
    "am": (5, 9, 0),
    "pm": (9, 13, 0),
    "cme": (15, 19, -1),
}
SDEV_NAMES = {"asia": "Asia", "ldn": "London", "am": "NY AM", "pm": "NY PM", "cme": "CME"}
THIRD = {1: "upper", 0: "middle", -1: "lower"}

COLORS = {
    "peth": "#B49AF0",
    "prth": "#8A919C",
    "ib": "#4C9BE8",
    "week": "#E9C46A",
    "open": "#C8962E",
    "up": "#3FB950",
    "down": "#E0574A",
    "hour": "#8A919C",
    "stretch": "#3FB950",
    "runaway": "#E0574A",
    "follow": "#E9C46A",
    "d": "#4B9A82",
    "w": "#D9A441",
    "m": "#C77DFF",
    "asia": "#E0574A",
    "london": "#5B7CFA",
}


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _pt(d: date, hour: int, minute: int = 0, day_offset: int = 0) -> int:
    base = datetime(d.year, d.month, d.day, tzinfo=PT) + timedelta(days=day_offset)
    # hour may run past 24 (London ends 5 AM the next morning)
    return _ms((base + timedelta(hours=hour, minutes=minute)).astimezone(timezone.utc))


def _fin(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def trading_day_for(ms: int) -> date:
    """The CME day a moment belongs to: 3 PM PT starts the next day; weekends roll to Monday."""
    local = datetime.fromtimestamp(ms / 1000, PT)
    d = local.date() + (timedelta(days=1) if local.hour >= 15 else timedelta())
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def day_window(d: date) -> tuple[int, int]:
    return _pt(d, 15, day_offset=-1), _pt(d, 14)


def previous_trading_day(d: date) -> date:
    p = d - timedelta(days=1)
    while p.weekday() > 4:
        p -= timedelta(days=1)
    return p


class _Bars:
    def __init__(self, rows: np.ndarray) -> None:
        rows = np.asarray(rows, dtype=float).reshape(-1, 5) if len(rows) else np.zeros((0, 5))
        self.t = rows[:, 0].astype(np.int64)
        self.o, self.h, self.l, self.c = rows[:, 1], rows[:, 2], rows[:, 3], rows[:, 4]

    def __len__(self) -> int:
        return len(self.t)

    def idx(self, ms: int) -> int:
        return int(np.searchsorted(self.t, ms))


# ----------------------------------------------------------------------------- daily helpers
def _cme_days(h1: _Bars) -> dict[date, list[float]]:
    days: dict[date, list[float]] = {}
    for i in range(len(h1)):
        k = (datetime.fromtimestamp(h1.t[i] / 1000, NY) + timedelta(hours=6)).date()
        d = days.setdefault(k, [h1.h[i], h1.l[i]])
        d[0], d[1] = max(d[0], h1.h[i]), min(d[1], h1.l[i])
    return days


def _adr(days: dict[date, list[float]], d: date, n: int = 14) -> float | None:
    prev = [v[0] - v[1] for k, v in sorted(days.items()) if k < d and k.weekday() < 5][-n:]
    return round(float(sum(prev) / len(prev)), 2) if prev else None


def _week_hl(days: dict[date, list[float]], d: date) -> tuple[float, float] | None:
    mon = d - timedelta(days=d.weekday())
    pmon = mon - timedelta(days=7)
    vals = [v for k, v in days.items() if pmon <= k < mon]
    if not vals:
        return None
    return max(v[0] for v in vals), min(v[1] for v in vals)


def _sdev_window(d: date, key: str) -> tuple[int, int]:
    a, b, off = SDEV_WINDOWS[key]
    return _pt(d, a, day_offset=off), _pt(d, b, day_offset=off)


def _sdev(h1: _Bars, days: dict[date, list[float]], d: date, key: str, n: int = 20) -> float | None:
    vals = []
    for k in sorted(days):
        if k >= d or k.weekday() > 4:
            continue
        a, b = _sdev_window(k, key)
        i, j = h1.idx(a), h1.idx(b)
        if j - i < (b - a) / HOUR_MS * 0.8:
            continue
        vals.append((h1.c[j - 1] - h1.o[i]) / h1.o[i] * 100)
    vals = vals[-n:]
    return st.pstdev(vals) if len(vals) >= 5 else None


# ----------------------------------------------------------------------------- hits
def _scan(lv: dict, bars: _Bars, touch: bool = False) -> None:
    lv["hitAt"] = None
    i = bars.idx(lv["frm"])
    if i >= len(bars) or bars.t[i] >= lv["until"]:
        lv["side"] = "up" if lv["price"] >= (bars.c[-1] if len(bars) else lv["price"]) else "dn"
        lv["never"] = i < len(bars)  # in the past with no bars: never; in the future: pending
        return
    lv["side"] = "up" if lv["price"] >= bars.o[i] else "dn"
    if lv.get("kind") == "open":
        return
    j = bars.idx(lv["until"])
    h, l = bars.h[i:j], bars.l[i:j]
    if touch:
        hit = (l <= lv["price"]) & (h >= lv["price"])
    elif lv["side"] == "up":
        hit = h >= lv["price"] + TICK
    else:
        hit = l <= lv["price"] - TICK
    k = np.flatnonzero(hit)
    if k.size:
        lv["hitAt"] = int(bars.t[i + k[0]])


def _missed_sessions(lv: dict, sessions: dict[str, list[int]]) -> list[str]:
    end = lv["hitAt"] if lv.get("hitAt") is not None else lv["until"]
    out = []
    for key, (a, b) in sessions.items():
        if b <= lv["frm"] or a >= end:
            continue
        if lv.get("hitAt") is not None and a <= lv["hitAt"] < b:
            continue
        out.append(SESSIONS[key][0])
    return out


# ----------------------------------------------------------------------------- one day
def _day_levels(d: date, bars: _Bars, BR: np.ndarray, HS: np.ndarray, h1: _Bars,
                days: dict[date, list[float]], X: dict | None = None) -> dict:
    X = X or {}
    start, end = day_window(d)
    rth0, ib1, rth1 = _pt(d, 6, 30), _pt(d, 7, 30), _pt(d, 13)
    i0 = bars.idx(start)
    last_i = bars.idx(end) - 1
    levels: list[dict] = []
    ctx: dict[str, Any] = {"rth0": rth0, "ib1": ib1, "rth1": rth1, "adr": _adr(days, d),
                           "ethOver": BREAK_RATES["eth"]["overnight"]}

    def add(**kw: Any) -> None:
        if _fin(kw.get("price")) is None:
            return
        kw["price"] = float(kw["price"])
        kw.setdefault("odds", None)
        kw.setdefault("kind", "target")
        levels.append(kw)

    if i0 >= len(bars) or bars.t[i0] >= end:
        return {"levels": levels, "ctx": ctx}

    # pETH: yesterday's full session
    eth = BREAK_RATES["eth"]
    es, et = _fin(BR[i0, BC["eth_setup"]]), _fin(BR[i0, BC["eth_third"]])
    hi_o = lo_o = None
    if es == 0 and et is not None:
        hi_o, lo_o = eth["inside"][THIRD[int(et)]]
        ctx["setupEth"] = f"Opened inside yesterday's range ({THIRD[int(et)]} third)"
    elif es is not None:
        ctx["setupEth"] = "Opened outside yesterday's range"
    for key, label, odds in (("h", "high", hi_o), ("l", "low", lo_o)):
        add(id=f"peth_{key}", group="pETH", label=f"Yesterday's {label} (pETH)", price=BR[i0, BC[f"peth_{key}"]],
            frm=start, until=end, odds=odds, color=COLORS["peth"],
            why=f"{ctx.get('setupEth', '')}: the {label} gets taken {odds}% of days" if odds is not None else None)

    # pRTH (odds post at the 6:30 open)
    ir = bars.idx(rth0)
    if ir < len(bars) and bars.t[ir] < rth1:
        rs, r3 = _fin(BR[ir, BC["rth_setup"]]), _fin(BR[ir, BC["rth_third"]])
        rth = BREAK_RATES["rth"]
        hi_r = lo_r = None
        if rs == 0 and r3 is not None:
            hi_r, lo_r = rth["inside"][THIRD[int(r3)]]
            ctx["setupRth"] = f"Opened inside yesterday's RTH ({THIRD[int(r3)]} third)"
        elif rs == 1:
            lo_r = round(100 - rth["gap_up"]["held"], 1)
            ctx["setupRth"] = "Gapped up above yesterday's RTH high"
        elif rs == -1:
            hi_r = round(100 - rth["gap_down"]["held"], 1)
            ctx["setupRth"] = "Gapped down below yesterday's RTH low"
        for key, label, odds in (("h", "high", hi_r), ("l", "low", lo_r)):
            add(id=f"prth_{key}", group="pRTH", label=f"Yesterday's RTH {label} (pRTH)", price=BR[ir, BC[f"prth_{key}"]],
                frm=start, oddsFrom=rth0, until=rth1, odds=odds, color=COLORS["prth"],
                why=f"{ctx['setupRth']}: gets hit {odds}% of days" if odds is not None else "Gap level: price opened past it")
    else:
        # before 6:30 the pRTH lines come from the last RTH session (the engine fills them on RTH bars)
        prev_rth = bars.idx(_pt(previous_trading_day(d), 13)) - 1
        if 0 <= prev_rth < len(bars):
            pr = np.flatnonzero(np.isfinite(BR[: prev_rth + 1, BC["rth_box_h"]]))
            j = pr[-1] if pr.size else None
            if j is not None:
                for key, label in (("h", "high"), ("l", "low")):
                    add(id=f"prth_{key}", group="pRTH", label=f"Yesterday's RTH {label} (pRTH)", price=BR[j, BC[f"rth_box_{key}"]],
                        frm=start, oddsFrom=rth0, until=rth1, color=COLORS["prth"], why="Odds post at the 6:30 AM open")

    # IB
    iib = bars.idx(ib1)
    if iib < len(bars) and bars.t[iib] < rth1 and _fin(BR[iib, BC["ib_h"]]) is not None:
        ibh, ibl, ibm, side = (float(BR[iib, BC[k]]) for k in ("ib_h", "ib_l", "ib_mid", "ib_side"))
        s_ = "above" if side >= 0 else "below"
        ibr = BREAK_RATES["ib"]
        ctx["ib"] = {"high": ibh, "low": ibl, "mid": ibm, "side": int(side)}
        for key, label, odds in (("h", "IB high", ibr[s_][0]), ("l", "IB low", ibr[s_][1])):
            add(id=f"ib_{key}", group="IB", label=label, price=ibh if key == "h" else ibl, frm=ib1, until=rth1, odds=odds,
                color=COLORS["ib"], why=f"IB closed {s_} its middle: the {label} breaks {odds}% of days")
        j = bars.idx(rth1)
        hh, hl = BR[iib:j, BC["ib_hit_h"]], BR[iib:j, BC["ib_hit_l"]]
        fh = float(np.nanmin(hh)) if np.isfinite(hh).any() else None
        fl = float(np.nanmin(hl)) if np.isfinite(hl).any() else None
        if fh is not None or fl is not None:
            up = fl is None or (fh is not None and fh <= fl)
            at = int(fh if up else fl)
            rng = ibh - ibl
            for k, mult, odds in (("med", 0.62, 50), ("p75", 1.18, 25)):
                p = ibh + mult * rng if up else ibl - mult * rng
                add(id=f"ibx_{k}", group="IB ext", label=f"IB {mult}x extension", price=round(p * 4) / 4, frm=at, until=rth1,
                    odds=odds, color=COLORS["ib"],
                    why=f"After the first IB break, {'half' if odds == 50 else '1 in 4'} of days run this far ({mult}x the IB range)")

    # Last week
    wk = _week_hl(days, d)
    if wk:
        for key, label, p in (("pwh", "Last week's high", wk[0]), ("pwl", "Last week's low", wk[1])):
            add(id=key, group="Week", label=label, price=p, frm=start, until=end, color=COLORS["week"],
                why="Weekly level: a big-picture magnet or wall")

    # Session SDEV bands
    for key in SDEV_WINDOWS:
        a, b = _sdev_window(d, key)
        j = bars.idx(a)
        if j >= len(bars) or bars.t[j] >= b:
            continue
        sd = _sdev(h1, days, d, key)
        name = SDEV_NAMES[key]
        op = float(bars.o[j])
        add(id=f"{key}_open", group="SDEV", label=f"{name} open", price=op, frm=a, until=b, kind="open",
            color=COLORS["open"], why=f"{name} session open: the session's SDEV bands hang from it")
        if sd is None:
            continue
        for k in (0.5, 1.0):
            for sgn, side_i in ((1, 0), (-1, 1)):
                odds = SDEV_HITS[key]["0.5" if k == 0.5 else "1"][side_i]
                mark = "+" if sgn > 0 else "-"
                add(id=f"{key}_{'u' if sgn > 0 else 'd'}{k:g}", group="SDEV", label=f"{name} {mark}{k:g} SD",
                    price=round(op * (1 + sgn * k * sd / 100) * 4) / 4, frm=a, until=b, odds=odds,
                    color=COLORS["up"] if sgn > 0 else COLORS["down"],
                    why=f"{name} reaches its {mark}{k:g} SD band {odds}% of sessions")

    # Hour stats: each hour's prior-hour high / low, and back to the open after a sweep
    seen: set[int] = set()
    for i in range(i0, last_i + 1):
        if _fin(HS[i, HC["open"]]) is None:
            continue
        local = datetime.fromtimestamp(bars.t[i] / 1000, NY)
        a = _ms(local.replace(minute=0, second=0, microsecond=0))
        if a in seen:
            continue
        seen.add(a)
        hod = local.hour
        lab = datetime.fromtimestamp(a / 1000, PT).strftime("%-I %p")
        sl = HOUR_SLICES.get(str(hod))
        setup = HS[i, HC["setup"]] == 1
        for key, label, col in (("hh", "high", "ph"), ("hl", "low", "pl")):
            first20 = f" Sweeps here come in the first 20 min {sl['high' if key == 'hh' else 'low'][0]:.0f}% of the time" if sl else ""
            odds = HOUR_SWEEP.get(hod, [None, None])[0 if key == "hh" else 1] if setup else None
            took = f" This hour takes it {odds}% of the time." if odds is not None else ""
            add(id=f"{key}_{a}", group="Hour", label=f"{lab} prior-hour {label}", price=HS[i, HC[col]], frm=a,
                until=a + HOUR_MS, hour=True, odds=odds, color=COLORS["hour"],
                why=f"Prior-hour {label}.{took}{first20}")
        # After a sweep: the MAE (stretch past the swept level) and, once back at the open,
        # the MFE (follow-through past the open on the other side). Hour Stats zones.
        j = min(bars.idx(a + HOUR_MS), last_i + 1) - 1
        side = _fin(HS[j, HC["side"]])
        if side is not None:
            br = int(HS[j, HC["breach_at"]])
            which = "high" if side > 0 else "low"
            for e, pct, odds in (("near", "median", 50.0), ("mid", "P75", 25.0), ("far", "P90", 10.0)):
                add(id=f"hz_{a}_s{e}", group="Hour zones", label=f"{lab} MAE {pct}", price=round(HS[j, HC[f"stretch_{e}"]] * 4) / 4,
                    frm=br, until=a + HOUR_MS, odds=odds, carry=False, color=COLORS["stretch"],
                    why=f"Swept the prior-hour {which}. Of hours that still came back to the open, {odds:g}% stretched this far past it first (MAE)")
            rv = _fin(HS[j, HC["revert_at"]])
            if rv is not None:
                for e, pct, odds in (("near", "median", 50.0), ("mid", "P75", 25.0), ("far", "P90", 10.0)):
                    add(id=f"hz_{a}_f{e}", group="Hour zones", label=f"{lab} MFE {pct}", price=round(HS[j, HC[f"follow_{e}"]] * 4) / 4,
                        frm=int(rv), until=a + HOUR_MS, odds=odds, carry=False, color=COLORS["follow"],
                        why=f"Back at the hour open. {odds:g}% of these hours then run this far past it on the other side (MFE)")
        rates = HOUR_RATES.get(str(hod), {})
        add(id=f"ho_{a}", group="Hour", label=f"Back to {lab} open", price=HS[i, HC["open"]], frm=a,
            until=a + HOUR_MS, hour=True, kind="hour_open", segs=rates.get("segs"), rev=rates.get("rev"), color=COLORS["open"])

    # Opens (Current Day OHL): back to the day (Globex) open from 6:30, to the RTH open from 7:30
    if bars.idx(rth0) < len(bars) and bars.t[bars.idx(rth0)] < rth1:
        add(id="day_open", group="Opens", label="Back to day open", price=bars.o[i0], frm=rth0, until=rth1,
            odds=OPEN_BACK["day"], touch=True, carry=False, color=COLORS["open"],
            why=f"Globex open (3 PM). RTH trades back to it {OPEN_BACK['day']}% of days")
        r0 = bars.idx(rth0)
        if bars.idx(ib1) < len(bars) and bars.t[bars.idx(ib1)] < rth1:
            add(id="rth_open", group="Opens", label="Back to RTH open", price=bars.o[r0], frm=ib1, until=rth1,
                odds=OPEN_BACK["rth"], touch=True, carry=False, color=COLORS["open"],
                why=f"6:30 open. After the IB, price comes back to it {OPEN_BACK['rth']}% of days")

    # ALN sessions: Asia and London ranges; at 5 AM the pattern sets the London break odds
    asia_a, asia_b = _pt(d, 17, day_offset=-1), _pt(d, 23, day_offset=-1)
    ldn_b = _pt(d, 5)
    ia, ib_ = bars.idx(asia_a), bars.idx(asia_b)
    il = bars.idx(ldn_b)
    if ib_ - ia > 60 and ib_ < len(bars):
        ah, al = float(bars.h[ia:ib_].max()), float(bars.l[ia:ib_].min())
        for key, label, p in (("h", "high", ah), ("l", "low", al)):
            add(id=f"asia_{key}", group="ALN", label=f"Asia {label}", price=p, frm=asia_b, until=end,
                color=COLORS["asia"], why=f"Asia range {label} (5-11 PM)")
        if il - ib_ > 60 and il < len(bars):
            lh, ll = float(bars.h[ib_:il].max()), float(bars.l[ib_:il].min())
            pat = _pattern(ah, al, lh, ll)
            stats = ALN_STATS[f"P{pat}"]
            ctx["aln"] = {"pattern": pat, "text": ALN_TEXT[pat]}
            for key, label, p in (("h", "high", lh), ("l", "low", ll)):
                odds = stats[label]
                add(id=f"ldn_{key}", group="ALN", label=f"London {label}", price=p, frm=ldn_b, until=_pt(d, 13),
                    odds=odds, color=COLORS["london"],
                    why=f"P{pat}: {ALN_TEXT[pat]}. NY takes London's {label} {odds}% of days")

    # MTF SDEV: the day's, week's and month's bands
    k = X["h1L"].idx(start) if X.get("h1L") is not None else 0
    MT = X.get("MT")
    if MT is not None and k < len(MT):
        for tf in ("d", "w", "m"):
            op = _fin(MT[k, MC[f"{tf}_open"]])
            if op is None:
                continue
            name = MTF_NAMES[tf]
            # hourly bars of this week / month before today (bands already hit there are done)
            col = MT[:, MC[f"{tf}_open"]]
            k0 = k
            while k0 > 0 and col[k0 - 1] == op:
                k0 -= 1
            hl_ = X["h1L"]
            ph = float(hl_.h[k0:k].max()) if k > k0 else -np.inf
            pl = float(hl_.l[k0:k].min()) if k > k0 else np.inf
            for m_ in (0.5, 1.0, 1.5):
                for sgn, side_i in ((1, 0), (-1, 1)):
                    mark = "+" if sgn > 0 else "-"
                    odds = MTF_HITS[tf][f"{m_:g}"][side_i]
                    band = float(MT[k, MC[f"{tf}_{mark}{m_:g}"]])
                    if (sgn > 0 and ph >= band + TICK) or (sgn < 0 and pl <= band - TICK):
                        continue
                    add(id=f"mtf_{tf}_{'u' if sgn > 0 else 'd'}{m_:g}", group=f"MTF {tf.upper()}",
                        label=f"{name} {mark}{m_:g} SD", price=round(MT[k, MC[f'{tf}_{mark}{m_:g}']] * 4) / 4,
                        frm=start, until=end, odds=odds, color=COLORS[tf],
                        why=f"The {name.lower()} reaches its {mark}{m_:g} SD band {odds}% of the time")

    # IB retrace (Breaks): the current leg's 40% ("In") and 60% lines and its start
    last = min(last_i, bars.idx(rth1) - 1)
    if last >= bars.idx(ib1) and _fin(BR[last, BC["rt_dir"]]) is not None:
        dr, s0, e0 = (float(BR[last, BC[c_]]) for c_ in ("rt_dir", "rt_start", "rt_end"))
        at = int(BR[last, BC["rt_end_at"]]) + 60_000
        leg = abs(e0 - s0)
        word = "up" if dr > 0 else "down"
        for key, frac, label, why in (
            ("40", 0.4, "IB pullback 40% (In)", f"Pullback into the {word} leg's 40-60% zone. After the first Out a new extreme came first 69% of the time"),
            ("60", 0.6, "IB pullback 60%", "Bottom of the pullback zone"),
            ("100", 1.0, "IB leg start (flip)", "Past the leg's start the trend flips"),
        ):
            add(id=f"rt_{key}", group="IB retrace", label=label, price=round((e0 - dr * frac * leg) * 4) / 4,
                frm=at, until=rth1, touch=key != "100", carry=False, color=COLORS["ib"], why=why)

    # TBR open fade: AMTB and the ALN TBR sessions
    for key, (name, a_h, b_h, off, color) in TBR_SESSIONS.items():
        a, b = _pt(d, a_h, day_offset=off), _pt(d, b_h, day_offset=off)
        out = X.get("AM") if key == "am" else X.get("TB", {}).get(key)
        if out is None:
            continue
        cols = AC if key == "am" else {**{f: TF[f] for f in TF}, "+0.25": TF["up"], "-0.25": TF["dn"], "touch_side": TF["side"]}
        i, j = bars.idx(a), min(bars.idx(b), last_i + 1)
        if i >= j or _fin(out[j - 1, cols["open"]]) is None:
            continue
        r = j - 1
        o = float(out[r, cols["open"]])
        st_ = TBR_ODDS[key]
        grp = "AMTB" if key == "am" else "TBR"
        tag = name if key == "am" else f"{name} TBR"
        if key != "ny":  # NY shares the 8:00 open with AMTB
            add(id=f"tbr_{key}_open", group=grp, label=f"{tag} open", price=o, frm=a, until=b, kind="open",
                carry=False, color=COLORS["open"], why=f"{tag} open")
        for sgn, side_i, col in ((1, 0, "+0.25"), (-1, 1, "-0.25")):
            add(id=f"tbr_{key}_{col}", group=grp, label=f"{tag} {col}", price=out[r, cols[col]], frm=a, until=b,
                odds=st_["line"][side_i], carry=False, color=color,
                why=f"{tag} {col} SDEV line: reached {st_['line'][side_i]}% of sessions")
        side = _fin(out[r, cols["touch_side"]])
        if side is None:
            continue
        t_at = int(out[r, cols["touch_at"]])
        hr = min((t_at - a) // HOUR_MS, 7)
        rate = TBR_RATES.get(key, {}).get(f"{int(side)},{hr}")
        back = rate[0] if rate else st_["back"]
        add(id=f"tbr_{key}_back", group=grp, label=f"{tag} back to open", price=o, frm=t_at + 60_000, until=b,
            odds=back, touch=True, carry=False, color=COLORS["open"],
            why=f"Touched the {'+' if side > 0 else '-'}0.25 line; {back}% of these sessions come back to the open")
        for zone, ends in (("stretch", (("near", "median", st_["s_med"]), ("mid", "P75", st_["s_p75"]), ("far", "P90", st_["s_p90"]))),
                           ("runaway", (("near", "median", st_["r_med"][0]), ("mid", "P75", st_["r_p75"][0])))):
            for e, lab, odds in ends:
                if zone == "stretch":
                    zl, why = f"stretch {lab}", f"Push past the line before coming back: {odds}% of touched sessions get here"
                else:
                    after = st_["r_med"][1] if lab == "median" else st_["r_p75"][1]
                    zl = f"No-return {lab}"
                    why = (f"{odds}% of touched sessions get here, and then only {after}% come back to the open "
                           f"({st_['not_r']}% do when it isn't reached)")
                add(id=f"tbr_{key}_{zone}_{e}", group=grp, label=f"{tag} {zl}", price=out[r, cols[f'{zone}_{e}']],
                    frm=t_at, until=b, odds=odds, carry=False, color=COLORS[zone], why=why)
        rv = _fin(out[r, cols["revert_at"]])
        if rv is not None:
            for e, lab, odds in (("near", "median", 50.0), ("mid", "P75", 25.0), ("far", "P90", 10.0)):
                add(id=f"tbr_{key}_follow_{e}", group=grp, label=f"{tag} follow-through {lab}",
                    price=out[r, cols[f'follow_{e}']], frm=int(rv), until=b, odds=odds, carry=False,
                    color=COLORS["follow"],
                    why=f"After coming back, {odds:g}% of sessions run this far past the open on the other side")

    # Day so far
    sl_ = slice(i0, last_i + 1)
    if last_i >= i0:
        ctx["dayOpen"], ctx["dayHigh"], ctx["dayLow"] = float(bars.o[i0]), float(bars.h[sl_].max()), float(bars.l[sl_].min())
        r0, r1 = bars.idx(rth0), min(bars.idx(rth1), last_i + 1)
        if r1 > r0:
            ctx["rthOpen"], ctx["rthHigh"], ctx["rthLow"] = float(bars.o[r0]), float(bars.h[r0:r1].max()), float(bars.l[r0:r1].min())
    return {"levels": levels, "ctx": ctx}


def _resolve(day: dict, bars: _Bars) -> None:
    """Hits, hour sweeps and the carry-over windows for one day's levels."""
    start, end = day["start"], day["end"]
    hours: dict[str, list[dict]] = {}
    for lv in day["levels"]:
        lv.setdefault("origUntil", lv["until"])
        if lv["kind"] != "open" and not lv.get("hour") and lv.get("carry", True):
            lv["until"] = end  # missed targets stay open for the rest of the day
        if lv["kind"] == "hour_open":
            continue
        _scan(lv, bars, touch=bool(lv.get("touch")))
        if lv.get("hour"):
            hours.setdefault(lv["id"].split("_")[1], []).append(lv)
    for lv in day["levels"]:
        if lv["kind"] != "hour_open":
            continue
        k = lv["id"].split("_")[1]
        sweeps = sorted((x for x in hours.get(k, []) if x.get("hitAt") is not None), key=lambda x: x["hitAt"])
        if not sweeps:
            lv["never"] = True
            lv["hitAt"] = None
            continue
        sw = sweeps[0]
        seg = min(2, (sw["hitAt"] - int(k)) // 60000 // 20)
        lv["frm"] = sw["hitAt"] + 60000
        lv["odds"] = lv["segs"][str(seg)][0] if lv.get("segs") else lv.get("rev")
        lv["sweep"] = {"id": sw["id"], "at": sw["hitAt"]}
        when = datetime.fromtimestamp(sw["hitAt"] / 1000, PT).strftime("%-I:%M %p")
        lv["why"] = (f"Swept the prior-hour {'high' if sw['id'].startswith('hh') else 'low'} at {when} "
                     f"(minutes {seg * 20}-{seg * 20 + 19}). From there it comes back to this hour's open {lv['odds']}% of the time.")
        if lv["frm"] >= lv["until"]:
            lv["never"] = True
            lv["hitAt"] = None
            continue
        _scan(lv, bars, touch=True)
    del start


def _path(bars: _Bars, start: int, end: int, step_ms: int = 300_000) -> list[list[float]]:
    """The day's price as [bucket start ms, high, low, close] per 5 minutes (for the panel's mini chart)."""
    i, j = bars.idx(start), bars.idx(end)
    out: list[list[float]] = []
    for k in range(i, j):
        b = int(bars.t[k] // step_ms * step_ms)
        if out and out[-1][0] == b:
            r = out[-1]
            r[1], r[2], r[3] = max(r[1], float(bars.h[k])), min(r[2], float(bars.l[k])), float(bars.c[k])
        else:
            out.append([b, float(bars.h[k]), float(bars.l[k]), float(bars.c[k])])
    return out


def _shell(d: date) -> dict:
    start, end = day_window(d)
    sessions = {}
    for key, (_, a, b, off) in SESSIONS.items():
        sessions[key] = [_pt(d, a, day_offset=off), _pt(d, b, day_offset=off)]
    return {"key": d.isoformat(), "label": datetime(d.year, d.month, d.day).strftime("%a %b %-d"),
            "start": start, "end": end, "sessions": sessions}


def build_plan(m1_rows: np.ndarray, h1_rows: np.ndarray, d: date, h1_long: np.ndarray | None = None) -> dict:
    """The Game Plan for trading day ``d`` from 1-minute bars (~5 weeks before it, for the TBR
    SDEVs), hourly bars (~6 weeks, for the SDEV, average day range and last week) and,
    optionally, ~14 months of hourly bars for the weekly and monthly SDEV bands."""
    bars, h1 = _Bars(m1_rows), _Bars(h1_rows)
    days = _cme_days(h1)
    X: dict[str, Any] = {}
    if len(bars):
        args = (bars.t, bars.o, bars.h, bars.l, bars.c)
        BR = breaks(*args)
        HS = hour_stats(*args)
        X["AM"] = am_tbr(*args)
        X["TB"] = {k: session_fade(*args, k) for k in TBR_SESSIONS if k != "am"}
    else:
        BR = HS = np.zeros((0, 64))
    hl = _Bars(h1_long if h1_long is not None else h1_rows)
    if len(hl):
        X["h1L"] = hl
        X["MT"] = mtf_sdev(hl.t, hl.o, hl.h, hl.l, hl.c, show={"d", "w", "m"})

    today = _shell(d)
    today.update(_day_levels(d, bars, BR, HS, h1, days, X) if len(bars) else {"levels": [], "ctx": {}})
    _resolve(today, bars)

    # Carry in what yesterday never touched
    p = previous_trading_day(d)
    for _ in range(4):  # skip holidays with no bars
        ps, pe = day_window(p)
        if len(bars) and bars.idx(pe) - bars.idx(ps) > 60:
            break
        p = previous_trading_day(p)
    prev = _shell(p)
    prev.update(_day_levels(p, bars, BR, HS, h1, days, X) if len(bars) else {"levels": []})
    _resolve(prev, bars)
    have = {lv["price"] for lv in today["levels"]}
    tag = prev["label"].split(" ")[0]
    for lv in prev["levels"]:
        if (lv["kind"] != "target" or lv.get("hour") or lv.get("never") or not lv.get("carry", True)
                or lv["group"] in ("Week", "MTF W", "MTF M")):
            continue
        if lv.get("hitAt") is not None or lv["price"] in have:
            continue
        have.add(lv["price"])
        missed = _missed_sessions(lv, prev["sessions"])
        carried = {**lv, "id": f"y_{lv['id']}", "label": f"{tag} {lv['label']}", "frm": today["start"], "until": today["end"],
                   "origUntil": today["start"], "odds": None, "oddsFrom": None, "fromDay": tag, "prevMissed": missed,
                   "why": f"Untouched all of {prev['label']} ({', '.join(missed) or 'every session'} missed it). Still open today."}
        _scan(carried, bars, touch=bool(carried.get("touch")))
        today["levels"].append(carried)

    li = bars.idx(today["end"]) - 1
    if len(bars) and li >= 0 and bars.t[li] >= today["start"]:
        today["last"] = {"t": int(bars.t[li]), "close": float(bars.c[li])}
    else:
        today["last"] = None
    today["path"] = _path(bars, today["start"], today["end"])
    for lv in today["levels"]:
        lv.pop("segs", None)
        lv.pop("rev", None)
        lv.pop("carry", None)
        lv.pop("touch", None)
        lv.setdefault("never", False)
    today["source"] = "ES 2016-2025"
    return today
