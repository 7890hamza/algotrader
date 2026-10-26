import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
from app import get_available_indicators
from app.services.candle_cache import CandleCache
from app.services.historical_indicator_service import run_historical_indicator

NY = ZoneInfo("America/New_York")


def candles() -> pd.DataFrame:
    """One night: Asia 100-110, London 105-115 (P3), New York trades up to 116."""
    start = datetime(2026, 10, 6, 20, 0, tzinfo=NY)
    rows, index = [], []
    for k in range(240):  # 20:00 -> 16:00 next day, 5-minute bars
        t = start + timedelta(minutes=5 * k)
        if k < 72:
            hi, lo = (110 if k == 5 else 101), 100
        elif k < 144:
            hi, lo = (115 if k == 80 else 107), 105
        else:
            hi, lo = (116 if k == 160 else 108), 106
        index.append(t)
        rows.append({"open": lo, "high": hi, "low": lo, "close": lo, "volume": 1.0})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index).tz_convert("UTC"))


class HistoricalAlnTests(unittest.IsolatedAsyncioTestCase):
    def test_listed(self) -> None:
        self.assertIn({"id": 8, "name": "ALN Sessions"}, get_available_indicators())

    async def test_response_has_boxes_pattern_and_guide(self) -> None:
        with patch(
            "app.services.historical_indicator_service.get_candles",
            AsyncMock(return_value=candles()),
        ):
            response = await run_historical_indicator(
                indicator_id=8,
                symbol="ES",
                exchange="CME",
                timeframe="M5",
                start_ms=None,
                end_ms=None,
                limit=500,
                custom_parameters={},
                candle_cache=CandleCache(),
            )
        info, rows = response["data"]["indicator_info"], response["data"]["indicator_data"]
        self.assertEqual(info["outputs"]["asia_high"]["type"], "box")
        self.assertEqual(info["guide"]["stats"]["P3"]["n"], 932)
        self.assertEqual(len(rows), 240)
        self.assertEqual(rows[0]["asia_high"], 101)
        self.assertIsNone(rows[0]["pattern"])
        ny = rows[150]
        self.assertEqual(ny["pattern"], 3)
        self.assertEqual(ny["ref_london_high"], 115)
        self.assertIsNone(ny["up_at"])
        self.assertIsNotNone(rows[-1]["up_at"])


if __name__ == "__main__":
    unittest.main()
