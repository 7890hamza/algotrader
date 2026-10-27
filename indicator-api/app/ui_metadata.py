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
        },
        # An arrow marks the first touch, on the line touched first only.
        "+0.25": {
            **level("AM TBR +0.25", SDEV_LEVEL_COLOR, "high"),
            "touchWhen": {"key": "touch_side", "equals": 1},
            "touchShape": "arrow",
            "touchColor": "#3FB950",
        },
        "-0.25": {
            **level("AM TBR -0.25", SDEV_LEVEL_COLOR, "low"),
            "touchWhen": {"key": "touch_side", "equals": -1},
            "touchShape": "arrow",
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
    ("asia", "Asia", "#E0574A", "5-11 PM", 75.6, 2366),
    ("ldn", "London", "#5B7CFA", "11 PM-5 AM", 77.4, 2396),
    ("am", "AM", "#3FB950", "5-9 AM", 75.8, 2419),
    ("pm", "PM", "#26A69A", "9 AM-1 PM", 74.9, 2363),
    ("ny", "NY", "#2E9E57", "5 AM-1 PM", 74.4, 2366),
]


def _aln_tbr_metadata() -> dict:
    """Open, +/- 0.25 and zones per ALN session, each in its session color."""
    zones = (
        ("stretch", "stretch (MAE)", 0.16),
        ("runaway", "no return (MAE)", 0.07),
        ("follow", "follow-through (MFE)", 0.11),
    )
    outputs: dict[str, dict] = {}
    for key, label, color, _, _, _ in ALN_TBR_SESSIONS:
        outputs[f"{key}_open"] = {
            "type": "level",
            "label": f"{label} Open",
            "labelColor": SDEV_LABEL_COLOR,
            "showPrice": True,
            "markerFrom": f"{key}_revert_at",
            "markerColor": "#F2D16B",
            "plotOptions": {"lineWidth": 1, "lineStyle": 0, "color": color},
        }
        for side, sign, touch, value, arrow in (
            ("up", "+", "high", 1, "#3FB950"),
            ("dn", "-", "low", -1, "#E0574A"),
        ):
            outputs[f"{key}_{side}"] = {
                "type": "level",
                "label": f"{label} {sign}0.25",
                "labelColor": SDEV_LABEL_COLOR,
                "showPrice": True,
                "touch": touch,
                "touchWhen": {"key": f"{key}_side", "equals": value},
                "touchShape": "arrow",
                "touchColor": arrow,
                "plotOptions": {"lineWidth": 1, "lineStyle": DOTTED, "color": color},
            }
        for zone, words, opacity in zones:
            for edge, share in (("near", "median"), ("far", "P90")):
                outputs[f"{key}_{zone}_{edge}"] = {
                    "type": "box",
                    "box": f"{key}_{zone}",
                    "edge": edge,
                    "label": f"{label} {words}",
                    "edgeLabel": f"{label} {words} · {share}",
                    "plotOptions": {"color": color, "fillOpacity": opacity},
                }
            outputs[f"{key}_{zone}_mid"] = {
                "type": "level",
                "label": f"{label} {words} · P75",
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
                "plotOptions": {"color": color, "lineWidth": 1},
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
}
