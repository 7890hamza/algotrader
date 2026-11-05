from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.candles import _fetch_candles_sync
from app.game_plan import build_plan, day_window, trading_day_for

router = APIRouter(prefix="/game-plan", tags=["game-plan"])


def _rows(df) -> np.ndarray:
    if df is None or df.empty:
        return np.zeros((0, 5))
    t = (pd.DatetimeIndex(df.index).as_unit("ns").asi8 // 1_000_000).astype(np.int64)
    return np.column_stack([t, df["open"].to_numpy(float), df["high"].to_numpy(float),
                            df["low"].to_numpy(float), df["close"].to_numpy(float)])


def _plan(symbol: str, exchange: Optional[str], d: date) -> dict:
    start, end = day_window(d)
    m1 = _fetch_candles_sync(symbol, "M1", start - 6 * 86_400_000, end, None, exchange)
    h1 = _fetch_candles_sync(symbol, "H1", start - 50 * 86_400_000, end, None, exchange)
    plan = build_plan(_rows(m1), _rows(h1), d)
    plan["symbol"] = symbol
    return plan


@router.get("/{symbol}")
async def get_game_plan(
    symbol: str,
    exchange: Optional[str] = Query(None, description="Market exchange"),
    day: Optional[str] = Query(None, description="Trading day YYYY-MM-DD (default: the current CME day)"),
) -> dict:
    """Every stat target for one CME day (3 PM - 2 PM Pacific): odds, hits, misses, carry-over."""
    try:
        d = date.fromisoformat(day) if day else trading_day_for(int(time.time() * 1000))
    except ValueError as e:
        raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD") from e
    if d.weekday() > 4:
        d -= timedelta(days=d.weekday() - 4)
    return await asyncio.to_thread(_plan, symbol, exchange, d)
