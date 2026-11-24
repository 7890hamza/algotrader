"""GEX (gamma exposure) levels for ES and NQ from free Yahoo Finance option chains.

What it does
  1. Downloads the SPX (for ES) and NDX (for NQ) option chains from Yahoo for the next ~5 weeks.
  2. For every strike: gamma (Black-Scholes, from Yahoo's implied volatility) x open interest x 100.
     Calls count as +, puts as -  (the usual "dealers are long calls, short puts" assumption).
     In dollars per 1% move:  gamma * OI * 100 * spot^2 * 0.01
  3. Finds:
       call wall  - the strike with the most + gamma (a ceiling / magnet)
       put wall   - the strike with the most - gamma (a floor / magnet)
       flip       - the price where total gamma changes sign. Above it: dealers dampen moves
                    ("rubber band", choppy). Below it: dealers add to moves ("gas pedal", fast).
       magnets    - the other biggest strikes
  4. Moves the levels from the index (SPX/NDX) onto the futures price (ES/NQ) using the gap
     between them right now, and writes frontend/public/gex/ES.json and NQ.json for the chart.

Limits (free data): open interest updates once a day (yesterday's close); Yahoo option prices
are ~15 minutes late; the + / - sign for calls and puts is an assumption, not the dealers' real
book. Treat the levels as areas, not exact prices.

Usage:  python scripts/gex.py            (once)
        python scripts/gex.py --loop 15  (again every 15 minutes, Ctrl+C to stop)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "gex"
MARKETS = {  # futures symbol: (index on Yahoo, futures on Yahoo, ETF fallback)
    "ES": ("^SPX", "ES=F", "SPY"),
    "NQ": ("^NDX", "NQ=F", "QQQ"),
}
MAX_DAYS = 35
SQRT2PI = math.sqrt(2 * math.pi)


@dataclass
class Opt:
    strike: float
    oi: float
    iv: float
    t: float  # years to expiry
    call: bool


def gamma(spot: float, strike: float, iv: float, t: float, r: float = 0.04) -> float:
    if spot <= 0 or strike <= 0 or iv <= 0 or t <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + iv * iv / 2) * t) / (iv * math.sqrt(t))
    return math.exp(-d1 * d1 / 2) / SQRT2PI / (spot * iv * math.sqrt(t))


def gex_at(opts: list[Opt], spot: float) -> dict[float, float]:
    """$ of futures the dealers must trade per 1% move, by strike (+ dampens, - adds)."""
    out: dict[float, float] = {}
    for o in opts:
        g = gamma(spot, o.strike, o.iv, o.t) * o.oi * 100 * spot * spot * 0.01
        out[o.strike] = out.get(o.strike, 0.0) + (g if o.call else -g)
    return out


def flip_point(opts: list[Opt], spot: float) -> float | None:
    """The price (within +/-10% of spot) where total gamma crosses zero, nearest to spot."""
    grid = [spot * (0.90 + 0.002 * i) for i in range(101)]
    tot = [sum(gex_at(opts, s).values()) for s in grid]
    best = None
    for (s0, g0), (s1, g1) in zip(zip(grid, tot), zip(grid[1:], tot[1:])):
        if g0 == 0 or (g0 < 0) != (g1 < 0):
            x = s0 if g0 == 0 else s0 + (s1 - s0) * g0 / (g0 - g1)
            if best is None or abs(x - spot) < abs(best - spot):
                best = x
    return best


def levels(opts: list[Opt], spot: float, n_magnets: int = 6) -> dict:
    by = gex_at(opts, spot)
    near = {k: v for k, v in by.items() if abs(k / spot - 1) <= 0.06}
    if not near:
        raise ValueError("no strikes near the price")
    call_wall = max(near, key=lambda k: near[k])
    put_wall = min(near, key=lambda k: near[k])
    total = sum(by.values())
    mags = sorted((k for k in near if k not in (call_wall, put_wall)), key=lambda k: -abs(near[k]))[:n_magnets]
    return {
        "total": total,
        "callWall": {"strike": call_wall, "gex": near[call_wall]},
        "putWall": {"strike": put_wall, "gex": near[put_wall]},
        "flip": flip_point(opts, spot),
        "magnets": [{"strike": k, "gex": near[k]} for k in sorted(mags)],
    }


# ---- Yahoo -----------------------------------------------------------------------------------
def years_to(expiry: str, now: datetime) -> float:
    close = datetime.fromisoformat(expiry).replace(hour=16, tzinfo=NY)
    return max((close - now).total_seconds(), 30 * 60) / (365 * 24 * 3600)


def fetch(index: str, now: datetime) -> tuple[list[Opt], float, list[str]]:
    import yfinance as yf

    t = yf.Ticker(index)
    spot = float(t.fast_info["last_price"])
    exps = [e for e in t.options if datetime.fromisoformat(e).date() <= (now + timedelta(days=MAX_DAYS)).date()]
    opts: list[Opt] = []
    exps = [e for e in exps if datetime.fromisoformat(e).replace(hour=16, tzinfo=NY) > now]  # skip ones already expired
    for e in exps:
        ch = t.option_chain(e)
        ty = years_to(e, now)
        for df, is_call in ((ch.calls, True), (ch.puts, False)):
            for k, oi, iv in zip(df["strike"], df["openInterest"].fillna(0), df["impliedVolatility"].fillna(0)):
                if oi > 0 and 0.03 < iv < 3:
                    opts.append(Opt(float(k), float(oi), float(iv), ty, is_call))
        time.sleep(0.3)  # be gentle with Yahoo
    return opts, spot, exps


def last_price(symbol: str) -> float:
    import yfinance as yf

    return float(yf.Ticker(symbol).fast_info["last_price"])


def build(market: str, now: datetime) -> dict:
    index, fut, etf = MARKETS[market]
    opts, spot, exps = fetch(index, now)
    source = index
    if len(opts) < 50:  # index chain empty on Yahoo: fall back to the ETF and scale
        e_opts, e_spot, exps = fetch(etf, now)
        scale = spot / e_spot
        opts = [Opt(o.strike * scale, o.oi / scale, o.iv, o.t, o.call) for o in e_opts]
        source = f"{etf} scaled to {index}"
    lv = levels(opts, spot)
    basis = last_price(fut) - spot  # futures minus index, to move strikes onto the ES/NQ chart
    move = lambda x: None if x is None else round(x + basis, 2)  # noqa: E731
    return {
        "market": market,
        "asOf": now.astimezone(timezone.utc).isoformat(),
        "source": source,
        "expirations": exps,
        "indexPrice": round(spot, 2),
        "basis": round(basis, 2),
        "regime": "positive" if lv["total"] > 0 else "negative",
        "totalGexBn": round(lv["total"] / 1e9, 2),
        "callWall": {"price": move(lv["callWall"]["strike"]), "strike": lv["callWall"]["strike"], "gexBn": round(lv["callWall"]["gex"] / 1e9, 2)},
        "putWall": {"price": move(lv["putWall"]["strike"]), "strike": lv["putWall"]["strike"], "gexBn": round(lv["putWall"]["gex"] / 1e9, 2)},
        "flip": move(lv["flip"]),
        "magnets": [{"price": move(m["strike"]), "strike": m["strike"], "gexBn": round(m["gex"] / 1e9, 2)} for m in lv["magnets"]],
    }


def run_once() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(NY)
    for market in MARKETS:
        try:
            data = build(market, now)
            (OUT / f"{market}.json").write_text(json.dumps(data, indent=1))
            print(f"{market}: {data['regime']} gamma, call wall {data['callWall']['price']}, put wall {data['putWall']['price']}, "
                  f"flip {data['flip']}  ({data['source']}, basis {data['basis']:+})")
        except Exception as exc:  # keep the other market going
            print(f"{market}: couldn't build GEX ({exc})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=float, default=0, help="minutes between refreshes (0 = once)")
    a = ap.parse_args()
    while True:
        run_once()
        if not a.loop:
            break
        time.sleep(a.loop * 60)
