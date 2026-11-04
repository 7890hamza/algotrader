"""Order commands on the MT5 bridge: off by default, demo accounts only."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.domain.value_objects import AccountId, OrderId, PositionId
from app.infrastructure.mt5_client import Mt5Client, OrderRejectedError, TradingDisabledError
from app.settings import Mt5Settings


class FakeTradingMt5:
    def __init__(self, *, demo: bool = True, retcode: int = 10009) -> None:
        self.demo = demo
        self.retcode = retcode
        self.sent: list[dict] = []
        self.positions = [
            SimpleNamespace(
                ticket=7,
                symbol="@EP",
                type=0,
                volume=2.0,
                price_open=7583.0,
                sl=7575.5,
                tp=7616.75,
                price_current=7590.0,
                profit=700.0,
                swap=0.0,
                time_msc=1,
                comment="AlgoTrader",
            )
        ]

    def initialize(self, path=None):
        return True

    def shutdown(self):
        return None

    def last_error(self):
        return (-1, "fake")

    def account_info(self):
        return SimpleNamespace(
            trade_mode=0 if self.demo else 2, server="Fake", company="F", balance=1.0, leverage=1
        )

    def symbol_select(self, name, enable):
        return True

    def symbol_info(self, name):
        return SimpleNamespace(filling_mode=2, digits=2, visible=True)

    def symbol_info_tick(self, name):
        return SimpleNamespace(bid=7589.75, ask=7590.0, time_msc=1)

    def order_send(self, request):
        self.sent.append(request)
        return SimpleNamespace(
            retcode=self.retcode,
            order=99,
            deal=0,
            price=request.get("price"),
            volume=request.get("volume", 0),
            comment="done" if self.retcode == 10009 else "no money",
        )

    def orders_get(self):
        return [
            SimpleNamespace(
                ticket=5,
                symbol="@EP",
                type=2,
                volume_current=1.0,
                price_open=7583.0,
                sl=7575.5,
                tp=7616.75,
                time_setup_msc=1,
                comment="",
            )
        ]

    def positions_get(self, ticket=None):
        return [p for p in self.positions if ticket is None or p.ticket == ticket]


def client(fake, trading: bool, require_demo: bool = True) -> Mt5Client:
    s = Mt5Settings(
        terminal_path=None,
        require_demo=require_demo,
        poll_interval_seconds=0.01,
        server_utc_offset_minutes=0,
        volume_source="real",
        symbol_aliases={"ES": "@EP"},
        history_settle_attempts=1,
        trading_enabled=trading,
    )
    return Mt5Client(s, mt5_module=fake)


ORDER = {
    "symbol": "ES",
    "orderType": "LIMIT",
    "tradeSide": "BUY",
    "volume": 1,
    "limitPrice": 7583.0,
    "stopLoss": 7575.5,
    "takeProfit": 7616.75,
}


class Mt5TradingTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_by_default(self) -> None:
        fake = FakeTradingMt5()
        c = client(fake, trading=False)
        with self.assertRaises(TradingDisabledError):
            await c.place_order(AccountId(1), ORDER)
        self.assertEqual(await c.get_open_positions(AccountId(1)), [])
        self.assertEqual(fake.sent, [])

    async def test_refuses_non_demo_even_when_on(self) -> None:
        fake = FakeTradingMt5(demo=False)
        c = client(fake, trading=True, require_demo=False)
        with self.assertRaises(TradingDisabledError):
            await c.place_order(AccountId(1), ORDER)
        self.assertEqual(fake.sent, [])

    async def test_limit_order_with_bracket(self) -> None:
        fake = FakeTradingMt5()
        c = client(fake, trading=True)
        result = await c.place_order(AccountId(1), ORDER)
        req = fake.sent[0]
        self.assertEqual(
            (req["symbol"], req["type"], req["price"], req["sl"], req["tp"]),
            ("@EP", 2, 7583.0, 7575.5, 7616.75),
        )
        self.assertEqual(result["orderId"], 99)

    async def test_market_order_uses_ask_and_rejection_is_reported(self) -> None:
        fake = FakeTradingMt5(retcode=10019)
        c = client(fake, trading=True)
        with self.assertRaises(OrderRejectedError) as ctx:
            await c.place_order(AccountId(1), {**ORDER, "orderType": "MARKET"})
        self.assertIn("10019", str(ctx.exception))
        self.assertEqual(fake.sent[0]["price"], 7590.0)

    async def test_positions_orders_close_cancel(self) -> None:
        fake = FakeTradingMt5()
        c = client(fake, trading=True)
        [pos] = await c.get_open_positions(AccountId(1))
        self.assertEqual(
            (pos.symbol, pos.trade_data.volume, pos.trade_data.trade_side), ("ES", 2, "BUY")
        )
        self.assertEqual(float(pos.profit), 700.0)
        [order] = await c.get_open_orders(AccountId(1))
        self.assertEqual((order.order_type, float(order.limit_price)), ("LIMIT", 7583.0))
        await c.close_position(AccountId(1), PositionId(7), None)
        self.assertEqual(
            (fake.sent[-1]["type"], fake.sent[-1]["position"], fake.sent[-1]["price"]),
            (1, 7, 7589.75),
        )
        await c.cancel_order(AccountId(1), OrderId(5))
        self.assertEqual(fake.sent[-1], {"action": 8, "order": 5})


if __name__ == "__main__":
    unittest.main()
