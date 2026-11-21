"""Preload 1-minute history from MT5 into the app's database, so the chart and Replay can go back.

Asks the running MT5 price bridge (broker-service) for each week from ``--start`` to now and saves
it through the database API. Running it again is safe: bars are saved by timestamp, so a repeat
just rewrites the same MT5 bars.

    python scripts/import_history.py                      # ES, NQ, MES, MNQ from Jan 1 this year
    python scripts/import_history.py --start 2021-01-01   # further back
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DAY = 86_400_000
WEEK = 7 * DAY


def get(url: str, headers: dict | None = None) -> object:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def post(url: str, body: dict) -> object:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=f"{datetime.now(timezone.utc).year}-01-01", help="YYYY-MM-DD")
    ap.add_argument("--symbols", default="ES,NQ,MES,MNQ")
    ap.add_argument("--db", default="http://localhost:8000", help="the app's database API")
    ap.add_argument("--mt5", default="http://localhost:8050", help="the MT5 price bridge")
    a = ap.parse_args()

    start = int(datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    try:
        markets = get(f"{a.db}/markets")
    except urllib.error.URLError as e:
        print(f"Can't reach the app's database at {a.db} ({e}). Start the app first.")
        return 1
    try:
        get(f"{a.mt5}/health")
    except urllib.error.URLError as e:
        print(f"Can't reach the MT5 price bridge at {a.mt5} ({e}). Start it (mt5-broker.bat) first.")
        return 1

    for symbol in [s.strip().upper() for s in a.symbols.split(",") if s.strip()]:
        market = next((m for m in markets if str(m["symbol"]).upper() == symbol
                       and "HYPER" not in str(m["exchange"]).upper()), None)
        if market is None:
            print(f"{symbol}: not in the app's symbol list, skipped")
            continue
        exchange = market["exchange"]
        # the database refuses the minute that is still open
        now = (int(time.time() * 1000) // 60_000) * 60_000 - 1
        total, empty_weeks = 0, 0
        print(f"{symbol}: loading from {a.start} ...", flush=True)
        t = start
        while t <= now:
            end = min(t + WEEK - 1, now)
            q = urllib.parse.urlencode({"timeframe": "M1", "fromTs": t, "toTs": end})
            try:
                bars = get(f"{a.mt5}/symbols/{symbol}/trendbars?{q}", {"X-Account-Id": "1"})
            except urllib.error.HTTPError as e:
                print(f"  {symbol}: MT5 said {e.code} for the week of "
                      f"{time.strftime('%Y-%m-%d', time.gmtime(t / 1000))}, skipped")
                bars = []
            candles = [{"timestamp_ms": int(b["t"]), "open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b.get("v") or 0}
                       for b in bars if t <= int(b["t"]) <= end]
            if candles:
                post(f"{a.db}/candles/historical", {
                    "symbol": symbol, "exchange": exchange, "candles": candles,
                    "start_ms": t, "end_ms": end,
                })
                total += len(candles)
            else:
                empty_weeks += 1
            print(f"  {symbol}: up to {time.strftime('%Y-%m-%d', time.gmtime(end / 1000))}, "
                  f"{total:,} bars", end="\r", flush=True)
            t = end + 1
        note = f" ({empty_weeks} weeks MT5 had nothing for)" if empty_weeks else ""
        print(f"  {symbol} done: {total:,} bars{note}                    ")
    print("Finished. Reload the chart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
