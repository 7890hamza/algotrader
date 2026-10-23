import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
from app import get_available_indicators
from app.services.candle_cache import CandleCache
from app.services.historical_indicator_service import run_historical_indicator
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def sessions(count: int) -> tuple[pd.DataFrame, list[float]]:
    days, day = [], datetime(2026, 9, 1, 5, 0, tzinfo=PACIFIC)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    changes = [0.05 * ((i * 7) % 9 - 4) for i in range(count)]
    index, opens, closes = [], [], []
    for i, start in enumerate(days):
        open_ = 7000.0 + i
        close = open_ * (1 + changes[i] / 100)
        for m in range(240):
            index.append(start + timedelta(minutes=m))
            opens.append(open_ if m == 0 else close)
            closes.append(close)
    frame = pd.DataFrame(
        dict(open=opens, high=closes, low=closes, close=closes, volume=1.0),
        index=pd.DatetimeIndex(index).tz_convert("UTC"),
    )
    return frame, changes


class HistoricalSessionSdevTests(unittest.IsolatedAsyncioTestCase):
    def test_listed_as_available(self) -> None:
        self.assertIn({"id": 6, "name": "Net Change SDEV"}, get_available_indicators())

    async def test_levels_are_returned_for_sessions_with_enough_history(self) -> None:
        candles, changes = sessions(22)
        with patch(
            "app.services.historical_indicator_service.get_candles",
            AsyncMock(return_value=candles),
        ):
            response = await run_historical_indicator(
                indicator_id=6,
                symbol="ES",
                exchange="CME",
                timeframe="M1",
                start_ms=None,
                end_ms=None,
                limit=500,
                custom_parameters={},
                candle_cache=CandleCache(),
            )
        info = response["data"]["indicator_info"]
        rows = response["data"]["indicator_data"]
        self.assertTrue(info["overlay"])
        self.assertEqual(info["outputs"]["+1"]["plotOptions"]["lineWidth"], 2)
        self.assertEqual(info["outputs"]["+0.25"]["plotOptions"]["lineStyle"], 2)
        self.assertEqual(len(rows), 2 * 240)  # sessions 21 and 22 have 20 complete before them
        sigma = float(np.std(changes[1:21], ddof=0))
        last = rows[-1]
        self.assertAlmostEqual(last["open"], 7021.0)
        self.assertAlmostEqual(last["-1"], 7021.0 * (1 - sigma / 100), places=6)


if __name__ == "__main__":
    unittest.main()
