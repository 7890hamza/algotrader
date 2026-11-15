"""Copy Hyperliquid 1-minute candles into our database so XYZ100 / SP500 chart like ES / NQ,
and compare them with the futures they track. Read-only on the Hyperliquid side."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from .hl import MAX_CANDLES, Coin, InfoClient, closed_minutes, tick_size

log = logging.getLogger("hyperliquid-service")
EXCHANGE = "HYPERLIQUID"
MINUTE = 60_000


def now_ms() -> int:
    return int(time.time() * 1000)


class Accessor:
    """The bits of the database accessor API we use."""

    def __init__(self, base: str, client: httpx.AsyncClient | None = None):
        self.base = base.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=30)

    async def has_market(self, symbol: str) -> bool:
        r = await self.client.get(f"{self.base}/markets", params={"symbol": symbol, "exchange": EXCHANGE})
        r.raise_for_status()
        return bool(r.json())

    async def create_market(self, symbol: str, min_move: float) -> None:
        r = await self.client.post(f"{self.base}/markets", json={
            "symbol": symbol, "exchange": EXCHANGE, "market_type": "perp",
            "min_move": min_move, "timezone": "UTC"})
        r.raise_for_status()

    async def latest(self, symbol: str, exchange: str | None = None) -> dict[str, Any] | None:
        params = {"exchange": exchange} if exchange else {}
        r = await self.client.get(f"{self.base}/candles/{symbol}/latest", params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def write(self, symbol: str, candles: list[dict[str, float]]) -> int:
        if not candles:
            return 0
        r = await self.client.post(f"{self.base}/candles/historical", json={
            "symbol": symbol, "exchange": EXCHANGE, "candles": candles,
            "start_ms": candles[0]["timestamp_ms"], "end_ms": candles[-1]["timestamp_ms"]})
        r.raise_for_status()
        return int(r.json().get("written_candles", len(candles)))


class Syncer:
    def __init__(self, info: InfoClient, accessor: Accessor, coins: list[Coin], backfill_days: float = 3.0):
        self.info, self.acc, self.coins = info, accessor, coins
        self.backfill_ms = int(backfill_days * 86_400_000)
        self.last_written: dict[str, int] = {}
        self.ctx: dict[str, dict[str, Any]] = {}
        self.updated_at = 0.0
        self.errors = 0

    async def refresh_ctx(self) -> None:
        for dex in sorted({c.dex for c in self.coins}):
            mk = await self.info.markets(dex)
            for c in self.coins:
                if c.coin in mk:
                    self.ctx[c.coin] = mk[c.coin]
        self.updated_at = time.time()

    async def ensure_markets(self) -> None:
        await self.refresh_ctx()
        for c in self.coins:
            if not await self.acc.has_market(c.symbol):
                m = self.ctx.get(c.coin, {})
                px = m.get("markPx") or 1.0
                await self.acc.create_market(c.symbol, tick_size(px, m.get("szDecimals", 0)))
                log.info("created market %s/%s", c.symbol, EXCHANGE)

    async def sync_coin(self, c: Coin) -> int:
        """Write every finished minute since the last one we stored (or the backfill window)."""
        end = now_ms()
        start = self.last_written.get(c.symbol)
        if start is None:
            latest = await self.acc.latest(c.symbol, EXCHANGE)
            start = int(latest["timestamp_ms"]) + MINUTE if latest else end - self.backfill_ms
        else:
            start += MINUTE
        written = 0
        while start < end:
            stop = min(end, start + (MAX_CANDLES - 1) * MINUTE)
            got = closed_minutes(await self.info.candles(c.coin, start, stop), now_ms())
            got = [k for k in got if k["timestamp_ms"] >= start]
            if got:
                written += await self.acc.write(c.symbol, got)
                self.last_written[c.symbol] = got[-1]["timestamp_ms"]
            start = stop + MINUTE
        return written

    async def compare(self) -> list[dict[str, Any]]:
        """Hyperliquid price vs the futures it tracks (last stored 1-minute close)."""
        out = []
        for c in self.coins:
            m = self.ctx.get(c.coin, {})
            hl = m.get("midPx") or m.get("markPx")
            fut = await self.acc.latest(c.compare) if c.compare else None
            row = {"coin": c.coin, "symbol": c.symbol, "hl_mid": hl, "hl_mark": m.get("markPx"),
                   "hl_oracle": m.get("oraclePx"), "funding_1h": m.get("funding"),
                   "futures": c.compare or None, "futures_close": None, "futures_time_ms": None,
                   "diff_pts": None, "diff_pct": None}
            if fut and hl:
                f = float(fut["close"])
                row.update(futures_close=f, futures_time_ms=int(fut["timestamp_ms"]),
                           diff_pts=round(hl - f, 2), diff_pct=round((hl / f - 1) * 100, 3))
            out.append(row)
        return out

    async def run(self, every_s: float = 20.0) -> None:
        while True:
            try:
                await self.ensure_markets() if not self.ctx else await self.refresh_ctx()
                for c in self.coins:
                    n = await self.sync_coin(c)
                    if n:
                        log.info("%s: wrote %d candles", c.symbol, n)
            except Exception as exc:  # keep running: network blips, accessor restarts
                self.errors += 1
                log.warning("sync failed: %s", exc)
            await asyncio.sleep(every_s)
