"""Hyperliquid service (read-only).

Copies trade.xyz's Nasdaq-100 (xyz:XYZ100) and S&P 500 (xyz:SP500) 1-minute candles into our
database as XYZ100 / SP500 on exchange HYPERLIQUID, so they chart and take indicators like ES / NQ,
and compares them with the futures (NQ / ES) from MT5.

It never holds keys and never sends orders.

HTTP :8040   /health   /markets   /compare
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager

from app.hl import MAINNET, InfoClient, parse_coins
from app.sync import Accessor, Syncer
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

COINS = parse_coins(os.environ.get("HL_COINS", "xyz:XYZ100=XYZ100>NQ, xyz:SP500=SP500>ES"))
syncer = Syncer(
    InfoClient(os.environ.get("HL_API", MAINNET)),
    Accessor(os.environ.get("DATA_ACCESSOR_URL", "http://database-accessor-api:8000")),
    COINS,
    backfill_days=float(os.environ.get("HL_BACKFILL_DAYS", "3")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(syncer.run(float(os.environ.get("HL_POLL_SECONDS", "20"))))
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await syncer.info.close()


app = FastAPI(title="hyperliquid-service", lifespan=lifespan)


@app.get("/health")
async def health():
    age = time.time() - syncer.updated_at if syncer.updated_at else None
    return {"status": "ok", "read_only": True, "coins": [c.coin for c in COINS],
            "last_update_s": round(age, 1) if age is not None else None,
            "last_written_ms": syncer.last_written, "errors": syncer.errors}


@app.get("/markets")
async def markets():
    return {c.coin: {"symbol": c.symbol, **syncer.ctx.get(c.coin, {})} for c in COINS}


@app.get("/compare")
async def compare():
    return await syncer.compare()
