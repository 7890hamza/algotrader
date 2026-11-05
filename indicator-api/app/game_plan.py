"""Game Plan: every stat target for one CME day, with what got hit, when, and what carried over.

The chart's Game Plan panel reads this. One CME day runs 3 PM - 2 PM Pacific (6 PM - 5 PM New
York). Targets come from the indicators already on the chart, with their ES 2016-2025 odds:

* pETH / pRTH  yesterday's full-session and RTH high / low (Breaks)
* IB           IB high / low from 7:30 AM, and the 0.62x / 1.18x extensions after the first break
* Week         last week's high / low
* SDEV         each ALN session's open and its +/-0.5 and +/-1 SDEV bands
* Hour         each hour's prior-hour high / low, and "back to the open" after a sweep

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
from indicator_engine.indicators.breaks import COL as BC
from indicator_engine.indicators.breaks import breaks
from indicator_engine.indicators.hour_stats import COL as HC
from indicator_engine.indicators.hour_stats import hour_stats
from zoneinfo import ZoneInfo

from app.ui_metadata import BREAK_RATES, HOUR_RATES, HOUR_SLICES

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
}

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
}
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
                days: dict[date, list[float]]) -> dict:
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
        name = SESSIONS[key][0]
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
        for key, label, col in (("hh", "high", "ph"), ("hl", "low", "pl")):
            first20 = f" Sweeps here come in the first 20 min {sl['high' if key == 'hh' else 'low'][0]:.0f}% of the time" if sl else ""
            add(id=f"{key}_{a}", group="Hour", label=f"{lab} prior-hour {label}", price=HS[i, HC[col]], frm=a,
                until=a + HOUR_MS, hour=True, color=COLORS["hour"], why=f"Prior-hour {label}.{first20}")
        rates = HOUR_RATES.get(str(hod), {})
        add(id=f"ho_{a}", group="Hour", label=f"Back to {lab} open", price=HS[i, HC["open"]], frm=a,
            until=a + HOUR_MS, hour=True, kind="hour_open", segs=rates.get("segs"), rev=rates.get("rev"), color=COLORS["open"])

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
        if lv["kind"] != "open" and not lv.get("hour"):
            lv["until"] = end  # missed targets stay open for the rest of the day
        if lv["kind"] == "hour_open":
            continue
        _scan(lv, bars)
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


def _shell(d: date) -> dict:
    start, end = day_window(d)
    sessions = {}
    for key, (_, a, b, off) in SESSIONS.items():
        sessions[key] = [_pt(d, a, day_offset=off), _pt(d, b, day_offset=off)]
    return {"key": d.isoformat(), "label": datetime(d.year, d.month, d.day).strftime("%a %b %-d"),
            "start": start, "end": end, "sessions": sessions}


def build_plan(m1_rows: np.ndarray, h1_rows: np.ndarray, d: date) -> dict:
    """The Game Plan for trading day ``d`` from 1-minute bars (covering the two days before it)
    and hourly bars (~6 weeks, for the SDEV, average day range and last week)."""
    bars, h1 = _Bars(m1_rows), _Bars(h1_rows)
    days = _cme_days(h1)
    if len(bars):
        BR = breaks(bars.t, bars.o, bars.h, bars.l, bars.c)
        HS = hour_stats(bars.t, bars.o, bars.h, bars.l, bars.c)
    else:
        BR = HS = np.zeros((0, 64))

    today = _shell(d)
    today.update(_day_levels(d, bars, BR, HS, h1, days) if len(bars) else {"levels": [], "ctx": {}})
    _resolve(today, bars)

    # Carry in what yesterday never touched
    p = previous_trading_day(d)
    for _ in range(4):  # skip holidays with no bars
        ps, pe = day_window(p)
        if len(bars) and bars.idx(pe) - bars.idx(ps) > 60:
            break
        p = previous_trading_day(p)
    prev = _shell(p)
    prev.update(_day_levels(p, bars, BR, HS, h1, days) if len(bars) else {"levels": []})
    _resolve(prev, bars)
    have = {lv["price"] for lv in today["levels"]}
    tag = prev["label"].split(" ")[0]
    for lv in prev["levels"]:
        if lv["kind"] != "target" or lv.get("hour") or lv.get("never") or lv["group"] == "Week":
            continue
        if lv.get("hitAt") is not None or lv["price"] in have:
            continue
        have.add(lv["price"])
        missed = _missed_sessions(lv, prev["sessions"])
        carried = {**lv, "id": f"y_{lv['id']}", "label": f"{tag} {lv['label']}", "frm": today["start"], "until": today["end"],
                   "origUntil": today["start"], "odds": None, "oddsFrom": None, "fromDay": tag, "prevMissed": missed,
                   "why": f"Untouched all of {prev['label']} ({', '.join(missed) or 'every session'} missed it). Still open today."}
        _scan(carried, bars)
        today["levels"].append(carried)

    li = bars.idx(today["end"]) - 1
    if len(bars) and li >= 0 and bars.t[li] >= today["start"]:
        today["last"] = {"t": int(bars.t[li]), "close": float(bars.c[li])}
    else:
        today["last"] = None
    for lv in today["levels"]:
        lv.pop("segs", None)
        lv.pop("rev", None)
        lv.setdefault("never", False)
    today["source"] = "ES 2016-2025"
    return today
