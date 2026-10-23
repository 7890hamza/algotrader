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
}
