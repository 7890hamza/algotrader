import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.hl import (  # noqa: E402
    Coin,
    InfoClient,
    closed_minutes,
    parse_candles,
    parse_coins,
    tick_size,
)
from app.sync import Syncer  # noqa: E402

# A real candleSnapshot row for xyz:XYZ100 (captured 2026-11-15).
ROW = {"T": 1794771299999, "c": "27724.0", "h": "27726.0", "i": "1m", "l": "27723.0", "n": 43,
       "o": "27724.0", "s": "xyz:XYZ100", "t": 1794771240000, "v": "2.0071"}


def test_parse_coins():
    coins = parse_coins("xyz:XYZ100=XYZ100>NQ, xyz:SP500=SP500>ES")
    assert coins[0] == Coin("xyz:XYZ100", "XYZ100", "NQ")
    assert coins[1].dex == "xyz" and coins[1].symbol == "SP500"


def test_tick_size_five_significant_figures():
    assert tick_size(27722.0, 4) == 1.0      # XYZ100 trades in whole points
    assert tick_size(7531.5, 3) == 0.1       # SP500 in tenths
    assert tick_size(138.88, 2) == 0.01


def test_parse_and_closed_minutes():
    c = parse_candles([ROW])
    assert c == [{"timestamp_ms": 1794771240000, "open": 27724.0, "high": 27726.0,
                  "low": 27723.0, "close": 27724.0, "volume": 2.0071}]
    assert closed_minutes(c, 1794771240000 + 30_000) == []          # still the open minute
    assert closed_minutes(c, 1794771300000) == c


class FakeAcc:
    def __init__(self):
        self.written, self.markets = [], {}

    async def has_market(self, s):
        return s in self.markets

    async def create_market(self, s, mm):
        self.markets[s] = mm

    async def latest(self, s, exchange=None):
        if s == "NQ":
            return {"timestamp_ms": 1794771240000, "close": 27850.0}
        return None

    async def write(self, s, candles):
        self.written.append((s, candles))
        return len(candles)


def _info(n_minutes=10):
    async def post(body):
        if body["type"] == "metaAndAssetCtxs":
            return [{"universe": [{"name": "xyz:XYZ100", "szDecimals": 4, "maxLeverage": 30}]},
                    [{"markPx": "27722.0", "oraclePx": "27687.0", "midPx": "27722.5", "funding": "0.00009"}]]
        req = body["req"]
        t0 = (req["startTime"] // 60000) * 60000
        rows = []
        for k in range(n_minutes):
            t = t0 + k * 60000
            if t > req["endTime"]:
                break
            rows.append({**ROW, "t": t})
        return rows
    return InfoClient(post=post)


def test_sync_creates_market_writes_and_compares():
    acc = FakeAcc()
    s = Syncer(_info(), acc, [Coin("xyz:XYZ100", "XYZ100", "NQ")], backfill_days=0.01)
    asyncio.run(s.ensure_markets())
    assert acc.markets == {"XYZ100": 1.0}
    n = asyncio.run(s.sync_coin(s.coins[0]))
    assert n > 0 and acc.written[0][0] == "XYZ100"
    stamps = [c["timestamp_ms"] for c in acc.written[0][1]]
    assert stamps == sorted(stamps) and all(t % 60000 == 0 for t in stamps)
    row = asyncio.run(s.compare())[0]
    assert row["hl_mid"] == 27722.5 and row["futures_close"] == 27850.0
    assert row["diff_pts"] == round(27722.5 - 27850.0, 2)
