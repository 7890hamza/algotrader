"""Read-only Hyperliquid client (public info API, no keys, no orders).

Coins on HIP-3 builder dexes are addressed as "<dex>:<name>", e.g. trade.xyz's
``xyz:XYZ100`` (Nasdaq-100) and ``xyz:SP500`` (S&P 500).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

MAINNET = "https://api.hyperliquid.xyz"
MAX_CANDLES = 5000  # the info API returns at most this many candles per request


@dataclass(frozen=True)
class Coin:
    coin: str      # Hyperliquid name, e.g. "xyz:XYZ100"
    symbol: str    # our chart symbol, e.g. "XYZ100"
    compare: str   # the futures symbol it tracks in our database, e.g. "NQ"

    @property
    def dex(self) -> str:
        return self.coin.split(":", 1)[0] if ":" in self.coin else ""


def parse_coins(raw: str) -> list[Coin]:
    """"xyz:XYZ100=XYZ100>NQ, xyz:SP500=SP500>ES" -> [Coin(...), ...]"""
    coins = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        coin, _, rest = part.partition("=")
        symbol, _, compare = rest.partition(">")
        name = coin.split(":")[-1]
        coins.append(Coin(coin.strip(), (symbol or name).strip().upper(), compare.strip().upper()))
    return coins


def tick_size(price: float, sz_decimals: int) -> float:
    """Smallest price step: Hyperliquid perp prices have at most 5 significant figures and
    at most 6 - szDecimals decimals."""
    if price <= 0:
        return 0.01
    sig = 10 ** (math.floor(math.log10(price)) - 4)
    dec = 10 ** -(6 - sz_decimals)
    return float(max(sig, dec))


def parse_candles(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    out = []
    for r in rows:
        out.append({
            "timestamp_ms": int(r["t"]),
            "open": float(r["o"]),
            "high": float(r["h"]),
            "low": float(r["l"]),
            "close": float(r["c"]),
            "volume": float(r.get("v") or 0.0),
        })
    out.sort(key=lambda c: c["timestamp_ms"])
    return out


def closed_minutes(candles: list[dict[str, float]], now_ms: int) -> list[dict[str, float]]:
    """Only finished 1-minute candles (the database refuses the open minute)."""
    open_minute = (now_ms // 60_000) * 60_000
    return [c for c in candles if c["timestamp_ms"] < open_minute]


Post = Callable[[dict[str, Any]], Awaitable[Any]]


class InfoClient:
    def __init__(self, base: str = MAINNET, client: httpx.AsyncClient | None = None, post: Post | None = None):
        self.base = base.rstrip("/")
        self._client = client
        self._post = post

    async def info(self, body: dict[str, Any]) -> Any:
        if self._post is not None:
            return await self._post(body)
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15)
        r = await self._client.post(f"{self.base}/info", json=body)
        r.raise_for_status()
        return r.json()

    async def markets(self, dex: str) -> dict[str, dict[str, Any]]:
        """name -> {szDecimals, maxLeverage, markPx, oraclePx, midPx, funding, openInterest, dayNtlVlm}"""
        meta, ctxs = await self.info({"type": "metaAndAssetCtxs", "dex": dex})
        out = {}
        for a, ctx in zip(meta["universe"], ctxs):
            row = {"szDecimals": int(a.get("szDecimals", 0)), "maxLeverage": a.get("maxLeverage")}
            for k in ("markPx", "oraclePx", "midPx", "funding", "openInterest", "dayNtlVlm", "prevDayPx"):
                v = ctx.get(k)
                row[k] = float(v) if v not in (None, "") else None
            out[a["name"]] = row
        return out

    async def candles(self, coin: str, start_ms: int, end_ms: int, interval: str = "1m") -> list[dict[str, float]]:
        rows = await self.info({"type": "candleSnapshot",
                                "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": end_ms}})
        return parse_candles(rows or [])

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
