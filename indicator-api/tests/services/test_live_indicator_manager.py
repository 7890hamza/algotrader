import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock

import pandas as pd
from app.schemas_live import LiveIndicatorStreamRequest
from app.services.candle_cache import CandleCache
from app.services.live_indicator_manager import LiveIndicatorManager


class LiveCandleCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_indicator_values_ignore_continuity_without_exposing_metadata(self):
        cache = CandleCache()
        cache.put(
            exchange=None,
            symbol="EURUSD",
            timeframe="M1",
            candles=pd.DataFrame(
                dict(
                    open=[1.0, 1.0],
                    high=[1.0, 1.0],
                    low=[1.0, 1.0],
                    close=[1.0, 1.0],
                    volume=[1.0, 1.0],
                ),
                index=pd.to_datetime([-60000, 0], unit="ms", utc=True),
            ),
        )
        queue = asyncio.Queue()

        async def read(*args, **kwargs):
            return await queue.get()

        redis = Mock(xread=AsyncMock(side_effect=read), xadd=AsyncMock(), close=AsyncMock())
        manager = LiveIndicatorManager(cache)
        manager._redis = redis
        request = LiveIndicatorStreamRequest(
            account_id="123",
            symbol="EURUSD",
            timeframe="M1",
            indicator_id=1,
            parameters={"window": 2},
        )
        try:
            started = await manager.start_stream(request)
            for i, metadata in enumerate(
                (
                    {},
                    {"continuity": "v1:" + "a" * 32},
                    {"continuity": "v1:" + "b" * 32},
                    {"continuity": "bad"},
                )
            ):
                fields = dict(
                    t=str((i + 1) * 60000), o="1", h="9", l="0", c=str(3 + i * 2), v="1", **metadata
                )
                await queue.put([("candles:123:EURUSD:M1", [(str(i + 1) + "-0", fields)])])
            async with asyncio.timeout(2):
                while redis.xadd.await_count < 4:
                    await asyncio.sleep(0)
            self.assertEqual(
                [json.loads(c.args[1]["d"])["sma"] for c in redis.xadd.call_args_list],
                [2.0, 4.0, 6.0, 8.0],
            )
            for call in redis.xadd.call_args_list:
                self.assertEqual(call.args[0], started.redis_stream_key)
                self.assertEqual(set(call.args[1]), {"t", "s", "i", "d"})
        finally:
            await manager.shutdown()


class SessionSdevLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_levels_with_less_history_than_warmup(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch

        import numpy as np
        from zoneinfo import ZoneInfo

        pacific = ZoneInfo("America/Los_Angeles")
        days, day = [], datetime(2026, 9, 1, 5, 0, tzinfo=pacific)
        while len(days) < 21:
            if day.weekday() < 5:
                days.append(day)
            day += timedelta(days=1)
        changes = [0.1 * ((i % 5) - 2) for i in range(20)]
        index, closes, opens = [], [], []
        for i, start in enumerate(days[:20]):
            open_ = 7000.0 + i
            close = open_ * (1 + changes[i] / 100)
            for m in range(240):
                index.append(start + timedelta(minutes=m))
                opens.append(open_ if m == 0 else close)
                closes.append(close)
        history = pd.DataFrame(
            dict(open=opens, high=closes, low=closes, close=closes, volume=1.0),
            index=pd.DatetimeIndex(index).tz_convert("UTC"),
        )
        queue = asyncio.Queue()

        async def read(*args, **kwargs):
            return await queue.get()

        redis = Mock(xread=AsyncMock(side_effect=read), xadd=AsyncMock(), close=AsyncMock())
        manager = LiveIndicatorManager(CandleCache())
        manager._redis = redis
        request = LiveIndicatorStreamRequest(
            account_id="1", symbol="ES", timeframe="M1", indicator_id=6, parameters={}
        )
        get_candles = AsyncMock(return_value=history)
        try:
            with patch("app.services.live_indicator_manager.get_candles", get_candles):
                started = await manager.start_stream(request)
            self.assertEqual(started.warmup.seeded_bars, len(history))
            five_am = int(days[20].timestamp() * 1000)
            await queue.put(
                [
                    (
                        "candles:1:ES:M1",
                        [
                            (
                                "1-0",
                                dict(t=str(five_am), o="7100", h="7101", l="7099", c="7100", v="1"),
                            )
                        ],
                    )
                ]
            )
            async with asyncio.timeout(5):
                while redis.xadd.await_count < 1:
                    await asyncio.sleep(0)
            values = json.loads(redis.xadd.call_args_list[-1].args[1]["d"])
            sigma = float(np.std(changes, ddof=0))
            self.assertAlmostEqual(values["open"], 7100.0)
            self.assertAlmostEqual(values["+1"], 7100.0 * (1 + sigma / 100), places=6)
        finally:
            await manager.shutdown()
