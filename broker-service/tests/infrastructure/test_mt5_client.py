from __future__ import annotations

import importlib.util
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from app.api.dependencies import get_account_id, get_market_data_service
from app.api.routers import market_data
from app.application.services import MarketDataService
from app.domain.models import Tick, Trendbar
from app.domain.value_objects import AccountId, Timeframe
from app.infrastructure.mt5_client import Mt5Client, TradingDisabledError
from app.infrastructure.stream_registry import StreamRegistry
from app.infrastructure.trendbar_stream_registry import TrendbarStreamRegistry
from app.settings import Mt5Settings, Settings, parse_symbol_aliases
from fastapi import FastAPI

MINUTE = 60


def rate(t: int, o: float, h: float, lo: float, c: float, tick_v: int = 5, real_v: int = 7):
    return {
        "time": t,
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "tick_volume": tick_v,
        "spread": 25,
        "real_volume": real_v,
    }


def tick(msc: int, bid: float, ask: float):
    return {"time": msc // 1000, "time_msc": msc, "bid": bid, "ask": ask, "last": bid}


class FakeMt5:
    """Minimal stand-in for the MetaTrader5 module (server clock = UTC)."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_H1 = 16385
    COPY_TICKS_ALL = -1

    def __init__(self, *, demo: bool = True) -> None:
        self.demo = demo
        self.connected = True
        self.rates: list[dict] = []
        self.ticks: list[dict] = []
        self.history_fail = False
        self.range_calls: list[tuple[datetime, datetime]] = []
        self.selected: list[str] = []

    def initialize(self, path=None):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (-1, "fake error")

    def account_info(self):
        return SimpleNamespace(
            trade_mode=0 if self.demo else 2,
            server="FakeServer-Demo",
            company="Fake",
            balance=1000.0,
            leverage=100,
        )

    def terminal_info(self):
        return SimpleNamespace(connected=self.connected)

    def symbol_info(self, name):
        if name == "@EP":
            return SimpleNamespace(name="@EP", digits=2, visible=False)
        return None

    def symbol_select(self, name, enable):
        self.selected.append(name)
        return True

    def symbols_get(self):
        return [SimpleNamespace(name="@EP"), SimpleNamespace(name="EURUSD")]

    def copy_rates_range(self, name, tf, start, end):
        if self.history_fail:
            return None
        self.range_calls.append((start, end))
        lo, hi = start.timestamp(), end.timestamp()
        return [r for r in self.rates if lo <= r["time"] <= hi]

    def copy_rates_from_pos(self, name, tf, pos, count):
        return self.rates[-count:]

    def symbol_info_tick(self, name):
        last = self.ticks[-1] if self.ticks else tick(0, 0, 0)
        return SimpleNamespace(time_msc=last["time_msc"], bid=last["bid"], ask=last["ask"])

    def copy_ticks_from(self, name, from_seconds, count, flags):
        return [t for t in self.ticks if t["time"] >= from_seconds][:count]


def settings(**overrides) -> Mt5Settings:
    values = dict(
        terminal_path=None,
        require_demo=True,
        poll_interval_seconds=0.01,
        server_utc_offset_minutes=0,
        volume_source="real",
        symbol_aliases={"ES": "@EP"},
        history_settle_attempts=1,
    )
    values.update(overrides)
    return Mt5Settings(**values)  # type: ignore[arg-type]


async def connected_client(fake: FakeMt5, **overrides) -> Mt5Client:
    client = Mt5Client(settings(**overrides), mt5_module=fake)
    await client._call(client._initialize)
    client._connected = True
    return client


class SettingsTests(unittest.TestCase):
    def test_parse_symbol_aliases(self) -> None:
        self.assertEqual(parse_symbol_aliases("es=@EP, NQ=@ENQ"), {"ES": "@EP", "NQ": "@ENQ"})

    def test_rejects_bad_alias(self) -> None:
        with self.assertRaises(ValueError):
            parse_symbol_aliases("@ES=@EP")
        with self.assertRaises(ValueError):
            parse_symbol_aliases("ES")


class Mt5ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_live_account_by_default(self) -> None:
        client = Mt5Client(settings(), mt5_module=FakeMt5(demo=False))
        with self.assertRaisesRegex(RuntimeError, "non-demo"):
            await client._call(client._initialize)

    async def test_live_account_allowed_when_opted_in(self) -> None:
        client = Mt5Client(settings(require_demo=False), mt5_module=FakeMt5(demo=False))
        await client._call(client._initialize)

    async def test_alias_symbol_and_listing(self) -> None:
        client = await connected_client(FakeMt5())
        symbol = await client.get_symbol(AccountId(1), "es")
        self.assertEqual((symbol.symbol_name, symbol.digits), ("ES", 2))
        self.assertIsNone(await client.get_symbol(AccountId(1), "NOPE"))
        names = [d.symbol_name for d in await client.list_symbols(AccountId(1))]
        self.assertEqual(names, ["ES", "EURUSD"])  # "@EP" is exposed only as its alias

    async def test_history_bounds_offset_and_volume(self) -> None:
        fake = FakeMt5()
        # Server clock is UTC+2h; bars at server 02:00..02:04 are UTC 00:00..00:04.
        base = 1_700_000_000 - 1_700_000_000 % 3600
        fake.rates = [
            rate(base + 7200 + i * MINUTE, 10 + i, 11 + i, 9 + i, 10.5 + i) for i in range(5)
        ]
        client = await connected_client(fake, server_utc_offset_minutes=120)
        bars = await client.get_trendbars(
            AccountId(1),
            "ES",
            Timeframe.M1,
            (base + MINUTE) * 1000,
            (base + 3 * MINUTE) * 1000,
            None,
        )
        self.assertEqual([b.t for b in bars], [(base + i * MINUTE) * 1000 for i in (1, 2, 3)])
        self.assertEqual(bars[0].v, 7)
        self.assertEqual(str(bars[0].o), "11.0")
        start, _ = fake.range_calls[0]
        self.assertEqual(start, datetime.fromtimestamp(base + 7200 + MINUTE, tz=timezone.utc))

    async def test_limit_keeps_newest(self) -> None:
        fake = FakeMt5()
        fake.rates = [rate(600 + i * MINUTE, 1, 2, 0.5, 1.5) for i in range(5)]
        client = await connected_client(fake, volume_source="tick")
        bars = await client.get_trendbars(AccountId(1), "ES", Timeframe.M1, 0, 10_000_000, 2)
        expected = [(600 + 3 * MINUTE) * 1000, (600 + 4 * MINUTE) * 1000]
        self.assertEqual([b.t for b in bars], expected)
        self.assertEqual(bars[0].v, 5)

    async def test_trading_is_disabled(self) -> None:
        client = await connected_client(FakeMt5())
        with self.assertRaises(TradingDisabledError):
            await client.place_order(AccountId(1), {"symbol": "ES"})
        with self.assertRaises(TradingDisabledError):
            await client.close_position(AccountId(1), 1)  # type: ignore[arg-type]
        self.assertEqual(await client.get_open_positions(AccountId(1)), [])
        accounts = await client.list_accounts()
        self.assertIsNone(accounts[0].trader_login)

    async def test_live_bars_publish_updates_and_final_closed_bar(self) -> None:
        fake = FakeMt5()
        client = await connected_client(fake)
        received: list[Trendbar] = []

        async def handler(bar: Trendbar) -> None:
            received.append(bar)

        await client.register_trendbar_handler(1, "ES", Timeframe.M1, handler)
        fake.rates = [rate(0, 1, 1, 1, 1), rate(60, 2, 2, 2, 2)]
        await client._poll_once()
        await client._poll_once()  # unchanged: nothing new
        fake.rates = [rate(0, 1, 1, 1, 1), rate(60, 2, 3, 2, 3)]
        await client._poll_once()
        fake.rates = [rate(60, 2, 4, 2, 3.5), rate(120, 3.5, 3.5, 3.5, 3.5)]
        await client._poll_once()
        self.assertEqual(
            [(b.t, float(b.h), float(b.c)) for b in received],
            [(60000, 2, 2), (60000, 3, 3), (60000, 4, 3.5), (120000, 3.5, 3.5)],
        )
        self.assertTrue(all(b.continuity and b.continuity.startswith("v1:") for b in received))

    async def test_live_ticks_are_not_duplicated_or_missed(self) -> None:
        fake = FakeMt5()
        fake.ticks = [tick(1_000, 1, 2)]
        client = await connected_client(fake)
        received: list[Tick] = []

        async def handler(t: Tick) -> None:
            received.append(t)

        await client.register_tick_handler(1, "ES", handler)
        await client._poll_once()  # anchors at the latest tick; history is not replayed
        self.assertEqual(received, [])
        fake.ticks += [tick(1_000, 1.25, 2), tick(1_500, 1.5, 2), tick(1_500, 1.75, 2)]
        await client._poll_once()
        fake.ticks += [tick(1_500, 2.0, 2.25), tick(2_200, 2.25, 2.5)]
        await client._poll_once()
        await client._poll_once()
        self.assertEqual([t.b for t in received], [1.25, 1.5, 1.75, 2.0, 2.25])
        self.assertEqual(received[-1].t, 2_200)

    async def test_disconnect_rotates_continuity(self) -> None:
        fake = FakeMt5()
        client = await connected_client(fake)
        before = client._continuity
        fake.connected = False
        with self.assertRaises(RuntimeError):
            await client._poll_once()
        client._mark_disconnected()
        self.assertNotEqual(before, client._continuity)
        self.assertFalse(client.is_connected)


# Load the real ingestion consumer without colliding with the broker's `app` package.
INGESTION = Path(__file__).resolve().parents[3] / "ingestion-service"
if "app.utils" not in sys.modules:
    _spec = importlib.util.spec_from_file_location("app.utils", INGESTION / "app/utils.py")
    assert _spec and _spec.loader
    _utils = importlib.util.module_from_spec(_spec)
    sys.modules["app.utils"] = _utils
    _spec.loader.exec_module(_utils)
_spec = importlib.util.spec_from_file_location(
    "mt5_history_consumer", INGESTION / "app/broker_client.py"
)
assert _spec and _spec.loader
consumer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(consumer)


class Mt5HistoryContractTests(unittest.IsolatedAsyncioTestCase):
    async def consume(self, fake: FakeMt5, start: int, end: int):
        client = await connected_client(fake)

        async def noop(*_args):
            return None

        base_settings = Settings()
        service = MarketDataService(
            client,
            StreamRegistry(noop, noop, noop, base_settings),  # type: ignore[arg-type]
            TrendbarStreamRegistry(noop, noop, noop, base_settings),  # type: ignore[arg-type]
        )
        app = FastAPI()
        app.include_router(market_data.router)
        app.dependency_overrides[get_account_id] = lambda: AccountId(1)
        app.dependency_overrides[get_market_data_service] = lambda: service
        http = consumer.BrokerClient("http://broker", "1")
        await http.async_client.aclose()
        http.async_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
        try:
            stream = http.stream_trendbars("ES", start_time=start, end_time=end)
            return [bar async for bar in stream]
        finally:
            http.close()
            await http.aclose()

    async def test_ingestion_accepts_mt5_history(self) -> None:
        fake = FakeMt5()
        fake.rates = [rate(i * MINUTE, 1, 2, 0.5, 1.5) for i in range(1, 6)]
        bars = await self.consume(fake, 60_000, 180_000)
        self.assertEqual([b["t"] for b in bars], [60_000, 120_000, 180_000])

    async def test_empty_interval_completes(self) -> None:
        bars = await self.consume(FakeMt5(), 60_000, 180_000)
        self.assertEqual(bars, [])

    async def test_provider_failure_is_not_success(self) -> None:
        fake = FakeMt5()
        fake.history_fail = True
        with self.assertRaises(RuntimeError):
            await self.consume(fake, 60_000, 180_000)

    async def test_long_backfill_is_windowed(self) -> None:
        fake = FakeMt5()
        now = int(time.time()) // 60 * 60
        fake.rates = [rate(now - 60 * 24 * 3600 + i * 3600, 1, 2, 0.5, 1.5) for i in range(5)]
        bars = await self.consume(fake, (now - 61 * 24 * 3600) * 1000, now * 1000)
        self.assertEqual(len(bars), 5)
        self.assertGreater(len(fake.range_calls), 1)


if __name__ == "__main__":
    unittest.main()
