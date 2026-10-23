from __future__ import annotations

SDEV_UP_COLOR = "#26A69A"
SDEV_DOWN_COLOR = "#EF5350"
SDEV_OPEN_COLOR = "#E8B04F"
SDEV_MULTIPLIERS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


def _session_sdev_metadata() -> dict:
    """Whole SDEVs solid and thick, halves solid, quarters dashed."""
    outputs: dict[str, dict] = {
        "open": {"type": "line", "plotOptions": {"lineWidth": 2, "color": SDEV_OPEN_COLOR}},
    }
    for m in SDEV_MULTIPLIERS:
        if float(m).is_integer():
            style = {"lineWidth": 2, "lineStyle": 0}
        elif (m * 2).is_integer():
            style = {"lineWidth": 1, "lineStyle": 0}
        else:
            style = {"lineWidth": 1, "lineStyle": 2}
        outputs[f"+{m:g}"] = {"type": "line", "plotOptions": {**style, "color": SDEV_UP_COLOR}}
        outputs[f"-{m:g}"] = {"type": "line", "plotOptions": {**style, "color": SDEV_DOWN_COLOR}}
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
    "session_sdev": _session_sdev_metadata(),
}
