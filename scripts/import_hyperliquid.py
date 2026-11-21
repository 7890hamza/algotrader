"""Load Hyperliquid 1-minute XYZ100 / SP500 history (from the Hydromancer archive via AWS) into the app.

Reads the CSV the AWS export made (symbol,time_ms,open,high,low,close,volume,trades) and saves it
through the database API, so the "CME closed" overlay and the catch-up trades can go back to
each market's first day. Bars are saved by timestamp, so running it again is safe.

The default file holds xyz:XYZ100 (from Oct 13, 2025) and xyz:SP500 (from Mar 18, 2026). Before
SP500 launched, its rows come from Dreamcash's cash:USA500 (Jan 20 - Mar 17, 2026), the S&P perp
that tracked ES most closely (15-minute moves 0.988 correlated); it trades about 6 pts above SP500.

    python scripts/import_hyperliquid.py [path-to-csv.gz]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT = os.path.expanduser(r"~\Downloads\Hyperliquid data 2026-11-20\hyperliquid_1m_XYZ100_SP500.csv.gz")


def call(url: str, body: dict | None = None) -> object:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST" if body else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=DEFAULT)
    ap.add_argument("--db", default="http://localhost:8000")
    ap.add_argument("--batch", type=int, default=20_000)
    a = ap.parse_args()
    if not os.path.exists(a.path):
        print(f"Can't find {a.path}")
        return 1
    try:
        markets = call(f"{a.db}/markets")
    except urllib.error.URLError as e:
        print(f"Can't reach the app's database at {a.db} ({e}). Start the app first.")
        return 1
    exchange = {str(m["symbol"]).upper(): m["exchange"] for m in markets if "HYPER" in str(m["exchange"]).upper()}
    rows: dict[str, list[dict]] = {}
    opener = gzip.open if a.path.endswith(".gz") else open
    with opener(a.path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["symbol"].upper(), []).append({
                "timestamp_ms": int(r["time_ms"]), "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"] or 0)})
    open_minute = (int(time.time() * 1000) // 60_000) * 60_000
    for symbol, candles in rows.items():
        if symbol not in exchange:
            print(f"{symbol}: not in the app's symbol list, skipped")
            continue
        candles = sorted((c for c in candles if c["timestamp_ms"] < open_minute), key=lambda c: c["timestamp_ms"])
        print(f"{symbol}: saving {len(candles):,} one-minute bars", flush=True)
        for k in range(0, len(candles), a.batch):
            part = candles[k:k + a.batch]
            call(f"{a.db}/candles/historical", {"symbol": symbol, "exchange": exchange[symbol], "candles": part,
                                                "start_ms": part[0]["timestamp_ms"], "end_ms": part[-1]["timestamp_ms"]})
            print(f"  {min(k + a.batch, len(candles)) * 100 // len(candles)}%", end="\r", flush=True)
        print(f"  {symbol} done          ")
    print("Finished. Reload the chart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
