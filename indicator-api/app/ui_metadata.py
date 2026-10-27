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

    return {
        "overlay": True,
        "outputs": {
            "open": level("TBR Open", SDEV_OPEN_COLOR),
            "+0.25": level("TBR +0.25", SDEV_LEVEL_COLOR, "high"),
            "-0.25": level("TBR -0.25", SDEV_LEVEL_COLOR, "low"),
        },
    }


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
        "high_after_low_first": 40.8
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
        "high_after_low_first": 58.3
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
        "high_after_low_first": 44.2
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
        "high_after_low_first": 42.1
    }
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
    for name in ("ref_asia_high", "ref_asia_low", "ref_london_high", "ref_london_low", "pattern",
                 "ny_open", "sdev_pts", "up_at", "dn_at", *[f"recent_{k}" for k in range(1, 9)]):
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
}
