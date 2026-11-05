from __future__ import annotations

SDEV_LEVEL_COLOR = "#4B9A82"
SDEV_OPEN_COLOR = "#C8962E"
SDEV_LABEL_COLOR = "#E6E6E6"
SDEV_MULTIPLIERS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
DOTTED = 1


def _session_sdev_metadata(open_label: str, label_prefix: str = "") -> dict:
    """Session levels drawn as labeled horizontal segments (output type "level").

    Clean style: thin dotted lines in one muted color, short white labels at the
    right end of each line, and a dotted gold open line.
    """
    prefix = f"{label_prefix} " if label_prefix else ""
    outputs: dict[str, dict] = {
        "open": {
            "type": "level",
            "label": open_label,
            "labelColor": SDEV_LABEL_COLOR,
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_OPEN_COLOR},
        },
    }
    for m in SDEV_MULTIPLIERS:
        for sign in ("+", "-"):
            outputs[f"{sign}{m:g}"] = {
                "type": "level",
                "label": f"{prefix}{sign}{m:g}",
                "labelColor": SDEV_LABEL_COLOR,
                "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_LEVEL_COLOR},
            }
    return {"overlay": True, "outputs": outputs}


def _am_tbr_metadata() -> dict:
    """TBR Open and +/- 0.25 SDEV in the SDEV style; a dot marks each line's first touch."""

    def level(label: str, color: str, touch: str | None = None) -> dict:
        out = {
            "type": "level",
            "label": label,
            "labelColor": SDEV_LABEL_COLOR,
            "showPrice": True,
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": color},
        }
        if touch:
            out["touch"] = touch
        return out

    zones = {
        # name: (box title, color)
        "stretch": ("Stretch (MAE)", "#3FB950"),
        "runaway": ("No return (MAE)", "#E0574A"),
        "follow": ("Follow-through (MFE)", "#E9C46A"),
    }
    outputs = {
        # A diamond marks where price came back to TBR Open after the first touch.
        "open": {
            **level("AM TBR Open", SDEV_OPEN_COLOR),
            "markerFrom": "revert_at",
            "markerColor": "#F2D16B",
            "markerText": "Back",
        },
        # An arrow marks the first touch, on the line touched first only.
        "+0.25": {
            **level("AM TBR +0.25", SDEV_LEVEL_COLOR, "high"),
            "touchWhen": {"key": "touch_side", "equals": 1},
            "touchShape": "arrow",
            "touchText": "Hit",
            "touchColor": "#3FB950",
        },
        "-0.25": {
            **level("AM TBR -0.25", SDEV_LEVEL_COLOR, "low"),
            "touchWhen": {"key": "touch_side", "equals": -1},
            "touchShape": "arrow",
            "touchText": "Hit",
            "touchColor": "#E0574A",
        },
    }
    for key, (title, color) in zones.items():
        for edge, words in (("near", "median"), ("far", "P90")):
            outputs[f"{key}_{edge}"] = {
                "type": "box",
                "box": f"tbr_{key}",
                "edge": edge,
                "label": title,
                "edgeLabel": f"{title} · {words}",
                "plotOptions": {"color": color, "fillOpacity": 0.16},
            }
        outputs[f"{key}_mid"] = {
            "type": "level",
            "label": f"{title} · P75",
            "labelColor": color,
            "showPrice": True,
            "extend": False,
            "plotOptions": {"lineWidth": 1, "lineStyle": 2, "color": color},
        }
    guide = {"kind": "tbr_am", "source": "ES 2016-2025", "rates": TBR_RATES["am"]}
    return {"overlay": True, "outputs": outputs, "guide": guide}


# Came back % and touched sessions by "side,hour since the session open" (side 1 = +0.25).
TBR_RATES: dict[str, dict[str, list[float]]] = {
    "cme": {
        "1,0": [74.7, 1269],
        "1,1": [30.3, 33],
        "-1,0": [74.6, 1029],
        "-1,1": [30.0, 40],
    },
    "asia": {
        "1,0": [75.8, 1019],
        "1,1": [68.2, 88],
        "1,2": [38.9, 18],
        "1,3": [26.7, 15],
        "1,4": [28.6, 7],
        "1,5": [0.0, 2],
        "-1,0": [80.3, 1100],
        "-1,1": [55.6, 81],
        "-1,2": [50.0, 22],
        "-1,3": [57.1, 7],
        "-1,4": [0.0, 3],
        "-1,5": [0.0, 4],
    },
    "ldn": {
        "1,0": [77.8, 911],
        "1,1": [73.9, 272],
        "1,2": [67.7, 31],
        "1,3": [80.0, 5],
        "1,4": [14.3, 7],
        "1,5": [0.0, 5],
        "-1,0": [81.1, 903],
        "-1,1": [75.6, 225],
        "-1,2": [52.2, 23],
        "-1,3": [50.0, 8],
        "-1,4": [0.0, 2],
        "-1,5": [25.0, 4],
    },
    "am": {
        "1,0": [80.8, 797],
        "1,1": [67.9, 355],
        "1,2": [57.5, 40],
        "1,3": [0.0, 6],
        "-1,0": [80.7, 844],
        "-1,1": [67.6, 343],
        "-1,2": [37.5, 32],
        "-1,3": [0.0, 2],
    },
    "pm": {
        "1,0": [75.3, 985],
        "1,1": [61.9, 134],
        "1,2": [41.7, 48],
        "1,3": [16.0, 25],
        "-1,0": [81.0, 1021],
        "-1,1": [64.8, 105],
        "-1,2": [68.6, 35],
        "-1,3": [30.0, 10],
    },
    "ny": {
        "1,0": [78.9, 558],
        "1,1": [70.2, 486],
        "1,2": [68.2, 88],
        "1,3": [40.0, 20],
        "1,4": [40.0, 10],
        "1,5": [25.0, 4],
        "1,6": [14.3, 7],
        "1,7": [0.0, 1],
        "-1,0": [81.3, 594],
        "-1,1": [73.1, 484],
        "-1,2": [61.7, 81],
        "-1,3": [60.0, 10],
        "-1,4": [85.7, 7],
        "-1,5": [50.0, 4],
        "-1,6": [62.5, 8],
        "-1,7": [0.0, 4],
    },
}


# ES 2016-2025 open fade by session: share of first +/-0.25 SDEV touches that came back
# to the session open before the session ended, and how many sessions were touched.
ALN_TBR_SESSIONS = [
    # key, label, color, window (Pacific), came back %, touched sessions
    ("cme", "CME", "#A78BFA", "3-5 PM", 73.3, 2371),
    ("asia", "Asia", "#E0574A", "5-11 PM", 75.6, 2366),
    ("ldn", "London", "#5B7CFA", "11 PM-5 AM", 77.4, 2396),
    ("am", "AM", "#3FB950", "5-9 AM", 75.8, 2419),
    ("pm", "PM", "#26A69A", "9 AM-1 PM", 74.9, 2363),
    ("ny", "NY", "#2E9E57", "5 AM-1 PM", 74.4, 2366),
]


def _aln_tbr_metadata() -> dict:
    """Each session drawn exactly like AM TBR: dotted open and +/-0.25 lines with white labels,
    a "Hit" arrow and a "Back" diamond, and the green stretch (MAE), red no-return (MAE) and
    gold follow-through (MFE) boxes with median / P75 / P90 labels."""
    zones = {
        "stretch": ("Stretch (MAE)", "#3FB950"),
        "runaway": ("No return (MAE)", "#E0574A"),
        "follow": ("Follow-through (MFE)", "#E9C46A"),
    }

    def level(label: str, color: str) -> dict:
        return {
            "type": "level",
            "label": label,
            "labelColor": SDEV_LABEL_COLOR,
            "showPrice": True,
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": color},
        }

    outputs: dict[str, dict] = {}
    for key, label, _color, _, _, _ in ALN_TBR_SESSIONS:
        name = f"{label} TBR"
        outputs[f"{key}_open"] = {
            **level(f"{name} Open", SDEV_OPEN_COLOR),
            "markerFrom": f"{key}_revert_at",
            "markerColor": "#F2D16B",
            "markerText": "Back",
        }
        for side, sign, touch, value, arrow in (
            ("up", "+", "high", 1, "#3FB950"),
            ("dn", "-", "low", -1, "#E0574A"),
        ):
            outputs[f"{key}_{side}"] = {
                **level(f"{name} {sign}0.25", SDEV_LEVEL_COLOR),
                "touch": touch,
                "touchWhen": {"key": f"{key}_side", "equals": value},
                "touchShape": "arrow",
                "touchText": "Hit",
                "touchColor": arrow,
            }
        for zone, (title, color) in zones.items():
            for edge, words in (("near", "median"), ("far", "P90")):
                outputs[f"{key}_{zone}_{edge}"] = {
                    "type": "box",
                    "box": f"{key}_{zone}",
                    "edge": edge,
                    "label": title,
                    "edgeLabel": f"{title} · {words}",
                    "plotOptions": {"color": color, "fillOpacity": 0.16},
                }
            outputs[f"{key}_{zone}_mid"] = {
                "type": "level",
                "label": f"{title} · P75",
                "labelColor": color,
                "showPrice": True,
                "extend": False,
                "plotOptions": {"lineWidth": 1, "lineStyle": 2, "color": color},
            }
    guide = {
        "kind": "tbr",
        "source": "ES 2016-2025",
        "sessions": [
            {
                "key": k,
                "label": lab,
                "color": col,
                "window": win,
                "cameBack": pct,
                "touched": n,
                "rates": TBR_RATES[k],
            }
            for k, lab, col, win, pct, n in ALN_TBR_SESSIONS
        ],
    }
    return {"overlay": True, "outputs": outputs, "guide": guide}


def _current_day_ohl_metadata() -> dict:
    """Three step lines like NinjaTrader's CurrentDayOHL: dashed open, green high, red low.

    lineType 1 draws steps, so the high and low jump outward when a new extreme
    prints and the lines jump to the new values when a session starts.
    """

    def line(title: str, color: str, style: int) -> dict:
        return {
            "type": "line",
            "plotOptions": {
                "color": color,
                "lineWidth": 1,
                "lineStyle": style,
                "lineType": 1,
                "title": title,
                "lastValueVisible": True,
            },
        }

    return {
        "overlay": True,
        "outputs": {
            "open": line("Open", "#E8A33D", 2),
            "high": line("High", "#3FB950", 0),
            "low": line("Low", "#E0574A", 0),
        },
    }


# ES 2016-2025 hour stats (AMP 1-minute): breaches of the prior hour high / low per New York
# hour, share that came back to the hour open before the hour ended, and the same by the
# segment of the breach ("0" = minutes 0-19, "1" = 20-39, "2" = 40-59) as [came back %, breaches].
HOUR_RATES: dict[str, dict] = {
    "8": {"n": 2068, "rev": 63.1, "segs": {"0": [73.8, 1373], "1": [48.8, 535], "2": [19.4, 160]}},
    "9": {"n": 2257, "rev": 74.3, "segs": {"0": [85.8, 1200], "1": [65.9, 907], "2": [34.0, 150]}},
    "10": {"n": 2152, "rev": 61.5, "segs": {"0": [70.5, 1687], "1": [36.0, 336], "2": [10.9, 129]}},
    "11": {"n": 1905, "rev": 56.4, "segs": {"0": [70.7, 1318], "1": [29.7, 390], "2": [13.7, 197]}},
    "12": {"n": 1894, "rev": 56.8, "segs": {"0": [69.7, 1305], "1": [36.2, 376], "2": [14.1, 213]}},
    "13": {"n": 1951, "rev": 58.9, "segs": {"0": [71.2, 1352], "1": [37.4, 409], "2": [18.4, 190]}},
    "14": {"n": 2024, "rev": 61.0, "segs": {"0": [71.8, 1481], "1": [39.8, 352], "2": [16.2, 191]}},
    "15": {"n": 2116, "rev": 67.6, "segs": {"0": [78.0, 1463], "1": [55.0, 393], "2": [28.5, 260]}},
}


# Share of prior-hour-high / -low breaks in each 20-minute slice (minutes 0-19 / 20-39 / 40-59),
# by New York hour, ES 2016-2025 (hours opening inside the prior hour's range).
HOUR_SLICES: dict[str, dict] = {
    "8": {"high": [55.8, 32.3, 11.9], "low": [57.0, 31.3, 11.7]},
    "9": {"high": [39.7, 44.5, 15.8], "low": [42.3, 40.3, 17.4]},
    "10": {"high": [72.4, 18.3, 9.3], "low": [71.9, 18.0, 10.1]},
    "11": {"high": [66.8, 21.3, 11.8], "low": [66.7, 20.9, 12.3]},
    "12": {"high": [66.9, 20.4, 12.7], "low": [65.1, 20.8, 14.1]},
    "13": {"high": [63.1, 23.0, 13.9], "low": [65.6, 21.3, 13.1]},
    "14": {"high": [66.0, 20.0, 14.0], "low": [71.5, 16.6, 11.9]},
    "15": {"high": [59.9, 20.2, 19.9], "low": [57.4, 20.8, 21.8]},
}


def _hour_stats_metadata() -> dict:
    """NQ Stats look: dotted gold open, grey prior-hour high / low with a pink arrow at the sweep
    and a blue diamond back at the open. The chart draws the sliced prior-hour box, the MAE /
    MFE bands and the hover card from the raw outputs (stretch_* = MAE, follow_* = MFE)."""
    grey = "#8A919C"
    outputs: dict[str, dict] = {
        "open": {
            "type": "level",
            "label": "Open",
            "labelColor": SDEV_LABEL_COLOR,
            "markerFrom": "revert_at",
            "markerColor": "#3B9CFF",
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": "#C8962E"},
        },
    }
    for key, label, touch, value in (("ph", "PHH", "high", 1), ("pl", "PHL", "low", -1)):
        outputs[key] = {
            "type": "level",
            "label": label,
            "labelColor": SDEV_LABEL_COLOR,
            "touch": touch,
            "touchWhen": {"key": "side", "equals": value},
            "touchShape": "arrow",
            "touchColor": "#D946EF",
            "plotOptions": {"lineWidth": 1, "lineStyle": 0, "color": grey},
        }
    guide = {"kind": "hour_stats", "source": "ES 2016-2025", "hours": HOUR_RATES, "slices": HOUR_SLICES}
    return {"overlay": True, "outputs": outputs, "guide": guide}

# Breaks (IB / RTH / ETH), ES 2016-2025 1-minute data. "upper" etc. are where the open sat
# inside the prior range (thirds) -> [high hit %, low hit %]. "held" = the far side never hit.
BREAK_RATES: dict = {
    "rth": {
        "inside": {"n": 1380, "either": 82.4, "one": 73.2, "both": 9.2,
                   "upper": [75.0, 22.8], "middle": [41.7, 37.7], "lower": [19.3, 78.6]},
        "gap_up": {"n": 628, "held": 88.4},
        "gap_down": {"n": 356, "held": 90.7},
    },
    "ib": {"n": 2307, "either": 98.1, "above": [83.3, 43.9, 1247], "below": [46.4, 81.8, 1045],
           "ext": [0.62, 1.18]},
    "eth": {
        "inside": {"n": 2164, "either": 86.9,
                   "upper": [80.0, 20.5], "middle": [48.0, 46.4], "lower": [24.3, 76.2]},
        # Seen from the 6:30 AM PT open: one side already hit overnight -> the other side held
        # 85.2%; neither hit yet -> one gets hit by 2 PM 64.2%.
        "overnight": {"other_held": 85.2, "n_one": 1335, "one_by_close": 64.2, "n_none": 794},
    },
}


def _breaks_metadata() -> dict:
    """pRTH (grey), IB (blue), pETH (purple dashed) lines with Hit arrows; boxes; odds chips."""
    grey, blue, purple, green = "#8A919C", "#4C9BE8", "#B49AF0", "#3FB950"

    def level(label: str, color: str, style: int = 0, touch: str | None = None,
              when: str | None = None, extend: bool = True) -> dict:
        out: dict = {
            "type": "level",
            "label": label,
            "labelColor": SDEV_LABEL_COLOR,
            "showPrice": True,
            "plotOptions": {"lineWidth": 1, "lineStyle": style, "color": color},
        }
        if touch:
            out.update(touch=touch, touchShape="arrow", touchText="Hit", touchColor=color)
        if when:
            out["touchWhen"] = {"key": when, "equals": 1}
        if not extend:
            out["extend"] = False
        out["joinGaps"] = True  # one line per session even across small gaps in the data
        return out

    outputs: dict[str, dict] = {
        "prth_h": level("pRTH High", grey, touch="high", when="rth_touch_h"),  # odds note + hover from the chart
        "prth_l": level("pRTH Low", grey, touch="low", when="rth_touch_l"),
        "ib_h": level("IB High", blue, touch="high"),
        "ib_l": level("IB Low", blue, touch="low"),
        "ib_mid": level("IB Mid", blue, style=1),
        "ib_ext_med": level("Half of days reach", green, style=1, extend=False),
        "ib_ext_p75": level("1 in 4 days reach", green, style=1, extend=False),
        "peth_h": level("pETH High", purple, style=2, touch="high", when="eth_touch_h"),
        "peth_l": level("pETH Low", purple, style=2, touch="low", when="eth_touch_l"),
    }
    # Each session's own range as a see-through labeled box: the next day's pRTH / pETH.
    for key, edge in (("rth_box_h", "high"), ("rth_box_l", "low")):
        outputs[key] = {"type": "box", "box": "rth_day", "edge": edge, "label": "RTH", "boxTitle": "pRTH",
                        "boxLabels": False, "joinGaps": True, "plotOptions": {"color": blue, "fillOpacity": 0.13}}
    for key, edge in (("eth_box_h", "high"), ("eth_box_l", "low")):
        outputs[key] = {"type": "box", "box": "eth_day", "edge": edge, "label": "ETH", "boxTitle": "pETH",
                        "boxLabels": False, "joinGaps": True, "plotOptions": {"color": purple, "fillOpacity": 0.07}}
    for key, edge in (("ib_box_h", "high"), ("ib_box_l", "low")):
        outputs[key] = {"type": "box", "box": "ib", "edge": edge, "label": "IB", "boxCompact": True,
                        "plotOptions": {"color": blue, "fillOpacity": 0}}
    guide = {"kind": "breaks", "source": "ES 2016-2025", "rates": BREAK_RATES,
             "retrace": {"zone": [0.4, 0.6], "up": "#3FB950", "down": "#E0574A", "leg": "#E9C46A"}}
    return {"overlay": True, "outputs": outputs, "guide": guide}


def _aln_sdev_metadata() -> dict:
    """The original SDEV look for every session: gold dotted "<Session> Open", green dotted
    ladder with short "+0.5" labels, each line drawn across its session's whole window."""
    windows = {"cme": 240, "asia": 360, "ldn": 360, "am": 240, "pm": 240}
    outputs: dict[str, dict] = {}
    for key, label, _color, _, _, _ in ALN_TBR_SESSIONS:
        if key not in windows:
            continue
        outputs[f"{key}_open"] = {
            "type": "level",
            "label": f"{label} Open",
            "labelColor": SDEV_LABEL_COLOR,
            "sessionMinutes": windows[key],
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_OPEN_COLOR},
        }
        for m in SDEV_MULTIPLIERS:
            for sign in ("+", "-"):
                outputs[f"{key}_{sign}{m:g}"] = {
                    "type": "level",
                    "label": f"{sign}{m:g}",
                    "labelColor": SDEV_LABEL_COLOR,
                    "sessionMinutes": windows[key],
                    "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_LEVEL_COLOR},
                }
    return {"overlay": True, "outputs": outputs}


MTF_TIMEFRAMES = (
    # key, label prefix, kept in the price scale's autoscale. Lines run to the latest bar so
    # every label lines up just right of price.
    ("d", "D", True),
    ("w", "W", False),
    ("m", "M", False),
    ("h4", "4H", True),
    ("h1", "1H", True),
)


def _mtf_sdev_metadata() -> dict:
    """The original SDEV look per timeframe ("D Open", "+0.5"; "W +0.5" for the others), the
    prior day / week high and low with Hit arrows, and the day-range bar."""
    grey = "#8A919C"
    outputs: dict[str, dict] = {}
    for key, label, scale in MTF_TIMEFRAMES:
        extra: dict = {} if scale else {"autoscale": False}
        if key in ("w", "m"):
            extra["joinGaps"] = True  # one line per week / month, through the daily CME break
        prefix = "" if key == "d" else f"{label} "
        outputs[f"{key}_open"] = {
            "type": "level", "label": f"{label} Open", "labelColor": SDEV_LABEL_COLOR,
            "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_OPEN_COLOR}, **extra,
        }
        for m in (0.5, 1.0, 1.5, 2.0):
            for sign in ("+", "-"):
                outputs[f"{key}_{sign}{m:g}"] = {
                    "type": "level", "label": f"{prefix}{sign}{m:g}", "labelColor": SDEV_LABEL_COLOR,
                    "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": SDEV_LEVEL_COLOR}, **extra,
                }
    for key, label, touch, when, scale in (
        ("pdh", "PDH", "high", "pd_touch_h", True), ("pdl", "PDL", "low", "pd_touch_l", True),
        ("pwh", "PWH", "high", "pw_touch_h", False), ("pwl", "PWL", "low", "pw_touch_l", False),
    ):
        outputs[key] = {
            "type": "level", "label": label, "labelColor": SDEV_LABEL_COLOR,
            "touch": touch, "touchWhen": {"key": when, "equals": 1}, "touchShape": "arrow",
            "touchText": "Hit", "touchColor": grey,
            "plotOptions": {"lineWidth": 1, "lineStyle": 0, "color": grey},
            **({} if scale else {"autoscale": False, "joinGaps": True}),
        }
    return {"overlay": True, "outputs": outputs, "guide": {"kind": "mtf_sdev", "rangeColor": "#378ADD"}}

def _engulfing_metadata() -> dict:
    """Engulfing candles are drawn by the chart's price primitive from the raw outputs."""
    return {
        "overlay": True,
        "outputs": {},
        "guide": {
            "kind": "engulfing",
            "rule": "Body covers the previous opposite body and is bigger; wicks ignored.",
            "invalidation": "A close beyond the engulfing candle's open.",
            "nearPoints": 2,
            "marubozu": "No wick on the open side; price tends to come back to its open.",
        },
    }


# ES statistics for the ALN guide: 2016-2025, AMP 1-minute data, New York session
# 08:00-16:00 New York time, a break = any trade one tick beyond the London level.
ALN_STATS = {
    "P1": {
        "n": 535,
        "share": 22.9,
        "high": 72.3,
        "low": 64.9,
        "both": 39.1,
        "neither": 1.9,
        "high_first": 54.0,
        "low_first": 43.6,
        "low_after_high_first": 38.4,
        "high_after_low_first": 40.8,
    },
    "P2": {
        "n": 129,
        "share": 5.5,
        "high": 80.6,
        "low": 69.8,
        "both": 50.4,
        "neither": 0.0,
        "high_first": 51.9,
        "low_first": 46.5,
        "low_after_high_first": 41.8,
        "high_after_low_first": 58.3,
    },
    "P3": {
        "n": 932,
        "share": 39.9,
        "high": 79.2,
        "low": 63.7,
        "both": 43.6,
        "neither": 0.6,
        "high_first": 62.9,
        "low_first": 36.2,
        "low_after_high_first": 43.3,
        "high_after_low_first": 44.2,
    },
    "P4": {
        "n": 739,
        "share": 31.6,
        "high": 67.3,
        "low": 73.9,
        "both": 42.5,
        "neither": 1.4,
        "high_first": 44.1,
        "low_first": 54.3,
        "low_after_high_first": 43.9,
        "high_after_low_first": 42.1,
    },
}


def _aln_metadata() -> dict:
    boxes = {"asia": ("#e0574a", "Asia"), "london": ("#5b7cfa", "London"), "ny": ("#3fb950", "NY")}
    outputs: dict[str, dict] = {}
    for key, (color, label) in boxes.items():
        for edge in ("high", "low"):
            outputs[f"{key}_{edge}"] = {
                "type": "box",
                "box": key,
                "edge": edge,
                "label": label,
                # Hollow: outline only, so the candles inside stay easy to read.
                "plotOptions": {"color": color, "lineWidth": 1, "fillOpacity": 0},
            }
    for name in (
        "ref_asia_high",
        "ref_asia_low",
        "ref_london_high",
        "ref_london_low",
        "pattern",
        "ny_open",
        "sdev_pts",
        "up_at",
        "dn_at",
        *[f"recent_{k}" for k in range(1, 9)],
    ):
        outputs[name] = {"type": "data"}
    return {
        "overlay": True,
        "outputs": outputs,
        "guide": {
            "kind": "aln",
            "stats": ALN_STATS,
            "colors": {"watch": "#e9c46a", "other": "#56606b"},
            "source": "ES 2016-2025",
        },
    }


UI_METADATA: dict[str, dict] = {
    "sma": {
        "overlay": True,
        "outputs": {
            "sma": {
                "type": "line",
                "plotOptions": {"lineWidth": 2, "color": "#FCFC4E"},
            }
        },
    },
    "rsi": {
        "overlay": False,
        "outputs": {
            "rsi": {
                "type": "line",
                "plotOptions": {"lineWidth": 2, "color": "#7E57C2"},
            }
        },
    },
    "bbands": {
        "overlay": True,
        "outputs": {
            "lower": {
                "type": "line",
                "plotOptions": {"lineWidth": 2, "color": "#089981"},
            },
            "mid": {
                "type": "line",
                "plotOptions": {"lineWidth": 2, "color": "#2962ff"},
            },
            "upper": {
                "type": "line",
                "plotOptions": {"lineWidth": 2, "color": "#f23645"},
            },
        },
    },
    "macd": {
        "overlay": False,
        "outputs": {
            "hist": {
                "type": "histogram",
                "plotOptions": {
                    "color": "#089981",
                    "priceFormat": {"minMove": 0.00001},
                },
            },
            "macd": {
                "type": "line",
                "plotOptions": {
                    "lineWidth": 2,
                    "color": "#2962ff",
                    "priceFormat": {"minMove": 0.00001},
                },
            },
            "signal": {
                "type": "line",
                "plotOptions": {
                    "lineWidth": 2,
                    "color": "#f23645",
                    "priceFormat": {"minMove": 0.00001},
                },
            },
        },
    },
    "currency_strength": {
        "overlay": False,
        "outputs": {
            "EUR": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#FF5252"}},
            "GBP": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#4CAF50"}},
            "JPY": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#00BCD4"}},
            "AUD": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#2962ff"}},
            "NZD": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#E040FB"}},
            "CAD": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#9C27B0"}},
            "CHF": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#880E4F"}},
            "USD": {"type": "line", "plotOptions": {"lineWidth": 2, "color": "#FF9800"}},
        },
    },
    "session_sdev": _session_sdev_metadata("NY Open"),
    "cme_open_sdev": _session_sdev_metadata("CME Open"),
    "aln_sessions": _aln_metadata(),
    "current_day_ohl": _current_day_ohl_metadata(),
    "am_tbr": _am_tbr_metadata(),
    "aln_tbr": _aln_tbr_metadata(),
    "engulfing": _engulfing_metadata(),
    "hour_stats": _hour_stats_metadata(),
    "breaks": _breaks_metadata(),
    "aln_sdev": _aln_sdev_metadata(),
    "mtf_sdev": _mtf_sdev_metadata(),
}
