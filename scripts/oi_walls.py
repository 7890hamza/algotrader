"""Option walls for NQ (from QQQ) and ES (from SPY): the STS "find key levels with QQQ" method.

The method (https://sts4x.com/learn/find-key-levels-with-qqq/), done by the script instead of by eye:
  Uses two expirations: today's (0DTE) and this Friday's weekly. Open interest is added together.
  1. Call wall        - the call strike ABOVE price with the most open interest
     Outer call wall  - the second-biggest call strike above price
  2. Put wall         - the put strike BELOW price with the most open interest
     Outer put wall   - the second-biggest put strike below price
  3. Flip             - between the walls, where calls stop outweighing puts (net call - put open
                        interest, smoothed over 3 strikes, changes sign; nearest one to price).
                        Above it dealers' hedging calms the market, below it adds fuel.
  4. Convert to futures (https://sts4x.com/learn/convert-qqq-levels-to-nq/):
       ratio = futures price / ETF price (NQ / QQQ is about 41), worked out with the FIRST refresh
       of the day and kept all day; level = strike x ratio, rounded to the nearest 5 NQ points
       (1 ES point). Each level is a zone: expect reactions within about 10-20 NQ points.

Because "above / below price" moves with price, the walls can step to new strikes during the day.
Each refresh is kept, so the chart can draw the step lines.

Writes:
  frontend/public/gex/walls_NQ.json, walls_ES.json   (the app's chart; last 10 days of steps)
  %USERPROFILE%/Documents/AlgoTraderLevels/NQ.csv, ES.csv   (the NinjaTrader indicator OiWalls)

Free data limits: Yahoo's open interest is from the previous close (it doesn't change during the
day); Yahoo prices can be a few minutes late, so conversions can be off by a few points.

Usage:  python scripts/oi_walls.py             (refresh every 5 minutes, Ctrl+C to stop)
        python scripts/oi_walls.py --once
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
APP_OUT = ROOT / "frontend" / "public" / "gex"
NT_OUT = Path.home() / "Documents" / "AlgoTraderLevels"
MARKETS = {"NQ": ("QQQ", "NQ=F"), "ES": ("SPY", "ES=F")}  # futures: (ETF with options, futures on Yahoo)
ROUND = {"NQ": 5.0, "ES": 1.0}  # STS: round NQ levels to the nearest 5 points
ZONE = {"NQ": 10.0, "ES": 2.5}  # half-width of the reaction zone drawn around each level
KEEP_DAYS = 10
APP_API = "http://localhost:8000/candles/{sym}/latest"


@dataclass
class Strike:
    k: float
    call_oi: float
    put_oi: float


@dataclass
class Walls:
    outer_call: float | None
    call: float | None
    flip: float | None
    put: float | None
    outer_put: float | None


def find_walls(strikes: list[Strike], price: float) -> Walls:
    """The 5 levels from open interest (ETF prices)."""
    s = sorted(strikes, key=lambda x: x.k)
    above = sorted((x for x in s if x.k > price and x.call_oi > 0), key=lambda x: -x.call_oi)
    below = sorted((x for x in s if x.k < price and x.put_oi > 0), key=lambda x: -x.put_oi)
    call = above[0].k if above else None
    outer_call = next((x.k for x in above[1:] if call is None or x.k > call), None)
    put = below[0].k if below else None
    outer_put = next((x.k for x in below[1:] if put is None or x.k < put), None)
    return Walls(outer_call, call, flip_between(s, put, call, price), put, outer_put)


def flip_between(s: list[Strike], lo: float | None, hi: float | None, price: float) -> float | None:
    """Where net (call - put) open interest turns from puts to calls, between the walls."""
    if lo is None or hi is None:
        return None
    inside = [x for x in s if lo <= x.k <= hi]
    if len(inside) < 2:
        return (lo + hi) / 2
    net = [x.call_oi - x.put_oi for x in inside]
    smooth = [sum(net[max(0, i - 1): i + 2]) for i in range(len(net))]
    best = None
    for i in range(len(inside) - 1):
        a, b = smooth[i], smooth[i + 1]
        if a <= 0 < b:  # puts dominate below, calls above
            x = inside[i].k + (inside[i + 1].k - inside[i].k) * (-a) / (b - a)
            if best is None or abs(x - price) < abs(best - price):
                best = x
    return best if best is not None else (lo + hi) / 2


def expirations(all_exps: list[str], today: date) -> list[str]:
    """Today's (0DTE) and this week's Friday (or the next one after today if none left)."""
    days = sorted(date.fromisoformat(e) for e in all_exps if date.fromisoformat(e) >= today)
    if not days:
        return []
    first = days[0]  # 0DTE when there's an expiry today, otherwise the next one
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    weekly = next((d for d in days if d >= friday), None)
    return sorted({first.isoformat(), *([weekly.isoformat()] if weekly else [])})


# ---- data -------------------------------------------------------------------------------------
def futures_price(market: str, yahoo_symbol: str) -> tuple[float, str]:
    """The app's own last price if it's running, otherwise Yahoo's."""
    try:
        with urllib.request.urlopen(APP_API.format(sym=market), timeout=3) as r:
            d = json.loads(r.read())
        c = d.get("close") or d.get("c")
        ts = d.get("timestamp_ms") or d.get("t") or 0
        if c and time.time() * 1000 - float(ts) < 15 * 60_000:  # only if the app's price is fresh
            return float(c), "app"
    except Exception:
        pass
    import yfinance as yf

    return float(yf.Ticker(yahoo_symbol).fast_info["last_price"]), "yahoo"


def chain(etf: str, today: date) -> tuple[list[Strike], float, list[str]]:
    import yfinance as yf

    t = yf.Ticker(etf)
    price = float(t.fast_info["last_price"])
    exps = expirations(list(t.options), today)
    by: dict[float, Strike] = {}
    for e in exps:
        ch = t.option_chain(e)
        for k, oi in zip(ch.calls["strike"], ch.calls["openInterest"].fillna(0)):
            by.setdefault(float(k), Strike(float(k), 0, 0)).call_oi += float(oi)
        for k, oi in zip(ch.puts["strike"], ch.puts["openInterest"].fillna(0)):
            by.setdefault(float(k), Strike(float(k), 0, 0)).put_oi += float(oi)
        time.sleep(0.3)
    return list(by.values()), price, exps


def snapshot(market: str, now: datetime, day_ratio: float | None = None) -> dict:
    etf, fut_sym = MARKETS[market]
    # after the 4 PM New York close today's options are done: look at the next day's
    day = now.date() + timedelta(days=1) if (now.hour, now.minute) >= (16, 15) else now.date()
    strikes, etf_price, exps = chain(etf, day)
    fut, src = futures_price(market, fut_sym)
    live_ratio = fut / etf_price
    ratio = day_ratio or live_ratio  # the morning's ratio is kept all day
    w = find_walls(strikes, etf_price)
    step = ROUND[market]
    conv = lambda x: None if x is None else round(x * ratio / step) * step  # noqa: E731
    return {
        "t": int(now.timestamp() * 1000),
        "etf": etf, "etfPrice": round(etf_price, 2), "futPrice": fut, "futSource": src, "ratio": round(ratio, 4), "liveRatio": round(live_ratio, 4), "zone": ZONE[market],
        "expirations": exps,
        "outerCall": conv(w.outer_call), "call": conv(w.call), "flip": conv(w.flip), "put": conv(w.put), "outerPut": conv(w.outer_put),
        "etfLevels": {"outerCall": w.outer_call, "call": w.call, "flip": w.flip, "put": w.put, "outerPut": w.outer_put},
    }


# ---- files ------------------------------------------------------------------------------------
def load_hist(market: str) -> dict:
    try:
        return json.loads((APP_OUT / f"walls_{market}.json").read_text())
    except Exception:
        return {"market": market, "days": {}}


def morning_ratio(market: str, now: datetime) -> float | None:
    """The ratio from today's first refresh, if there was one."""
    snaps = load_hist(market)["days"].get(now.date().isoformat())
    return snaps[0]["ratio"] if snaps else None


def save(market: str, snap: dict) -> None:
    APP_OUT.mkdir(parents=True, exist_ok=True)
    path = APP_OUT / f"walls_{market}.json"
    hist = load_hist(market)
    day = datetime.fromtimestamp(snap["t"] / 1000, NY).date().isoformat()
    hist["days"].setdefault(day, []).append(snap)
    for old in sorted(hist["days"])[:-KEEP_DAYS]:
        del hist["days"][old]
    hist["latest"] = snap
    path.write_text(json.dumps(hist))

    NT_OUT.mkdir(parents=True, exist_ok=True)
    csv = NT_OUT / f"{market}.csv"
    new = not csv.exists()
    with csv.open("a", encoding="utf-8") as f:
        if new:
            f.write("time_utc,outer_call,call,flip,put,outer_put\n")
        stamp = datetime.fromtimestamp(snap["t"] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        vals = [snap[k] for k in ("outerCall", "call", "flip", "put", "outerPut")]
        f.write(stamp + "," + ",".join("" if v is None else f"{v:.2f}" for v in vals) + "\n")


def run_once(live_ratio: bool = False) -> None:
    now = datetime.now(NY)
    for market in MARKETS:
        try:
            s = snapshot(market, now, None if live_ratio else morning_ratio(market, now))
            save(market, s)
            print(f"{now:%H:%M} {market}: outer call {s['outerCall']} | call {s['call']} | flip {s['flip']} | put {s['put']} | outer put {s['outerPut']}"
                  f"   ({s['etf']} {s['etfPrice']} x {s['ratio']}, {', '.join(s['expirations'])})")
        except Exception as exc:
            print(f"{now:%H:%M} {market}: couldn't refresh ({exc})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=float, default=5, help="minutes between refreshes")
    ap.add_argument("--live-ratio", action="store_true", help="recompute the NQ/QQQ ratio every refresh instead of once a morning")
    a = ap.parse_args()
    while True:
        run_once(a.live_ratio)
        if a.once:
            break
        time.sleep(a.every * 60)
