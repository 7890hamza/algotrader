"""Load years of 1-minute history from the NinjaTrader exports into the app's database.

The chart then scrolls (and Replay jumps) back as far as this goes. Only bars before the first
bar already in the database are written, so the MT5 feed's own bars are never touched; running
it again is safe (the database merges by timestamp).

    python scripts/import_history.py --years 5
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

DAY = 86_400_000
# market in the app -> NinjaTrader export it takes prices from (micros trade at the same price)
SOURCES = {"ES": "ES", "MES": "ES", "NQ": "NQ", "MNQ": "NQ"}


def get(api: str, path: str, **params) -> object:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{api}{path}?{query}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())


def post(api: str, path: str, body: dict) -> object:
    req = urllib.request.Request(f"{api}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def has_bars(api: str, symbol: str, exchange: str, day_ms: int) -> bool:
    rows = get(api, f"/candles/{symbol}", exchange=exchange, timeframe="M1",
               start_ms=day_ms, end_ms=day_ms + 7 * DAY)
    return isinstance(rows, list) and len(rows) > 0


def first_bar_ms(api: str, symbol: str, exchange: str, lo: int, hi: int) -> int:
    """Earliest week with bars (assumes the stored history has no gaps of more than a week)."""
    if has_bars(api, symbol, exchange, lo):
        return lo
    if not has_bars(api, symbol, exchange, hi - 7 * DAY):
        return hi
    while hi - lo > 7 * DAY:
        mid = (lo + hi) // 2
        if has_bars(api, symbol, exchange, mid):
            hi = mid
        else:
            lo = mid
    rows = get(api, f"/candles/{symbol}", exchange=exchange, timeframe="M1",
               start_ms=lo, end_ms=hi + 7 * DAY)
    return min(int(r["timestamp_ms"]) for r in rows) if rows else hi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=5)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--data", default=os.path.expanduser(r"~\es-sdev\data\processed"))
    ap.add_argument("--symbols", default="ES,NQ,MES,MNQ")
    ap.add_argument("--batch", type=int, default=20_000)
    a = ap.parse_args()

    try:
        markets = get(a.api, "/markets")
    except urllib.error.URLError as e:
        print(f"Can't reach the app's database at {a.api} ({e}). Start the app first.")
        return 1
    now = int(time.time() * 1000)
    start = now - int(a.years * 365.25 * DAY)
    for symbol in [s.strip().upper() for s in a.symbols.split(",") if s.strip()]:
        market = next((m for m in markets if str(m["symbol"]).upper() == symbol
                       and "HYPER" not in str(m["exchange"]).upper()), None)
        if market is None:
            print(f"{symbol}: not in the app's symbol list, skipped (add it with + first)")
            continue
        files = sorted(glob.glob(os.path.join(a.data, f"{SOURCES[symbol]}_m1_*.npz")))
        if not files:
            print(f"{symbol}: no {SOURCES[symbol]}_m1_*.npz in {a.data}, skipped")
            continue
        exchange = market["exchange"]
        until = first_bar_ms(a.api, symbol, exchange, start, now)
        with np.load(files[-1], allow_pickle=True) as z:  # read each column once
            t = z["t"].astype(np.int64)
            o, h, lo, c, v = (z[k].astype(float) for k in ("o", "h", "l", "c", "v"))
        keep = (t >= start) & (t < until)
        idx = np.where(keep)[0]
        print(f"{symbol}: writing {len(idx):,} bars from {files[-1].split(os.sep)[-1]} "
              f"({time.strftime('%Y-%m-%d', time.gmtime(start / 1000))} to "
              f"{time.strftime('%Y-%m-%d', time.gmtime(until / 1000))})", flush=True)
        done = 0
        for k in range(0, len(idx), a.batch):
            w = idx[k:k + a.batch]
            candles = [{"timestamp_ms": int(t[i]), "open": o[i], "high": h[i], "low": lo[i],
                        "close": c[i], "volume": v[i]} for i in w.tolist()]
            post(a.api, "/candles/historical", {
                "symbol": symbol, "exchange": exchange, "candles": candles,
                "start_ms": candles[0]["timestamp_ms"], "end_ms": candles[-1]["timestamp_ms"],
            })
            done += len(w)
            print(f"  {done * 100 // len(idx)}%", end="\r", flush=True)
        print(f"  {symbol} done          ")
    print("Finished. Reload the chart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
