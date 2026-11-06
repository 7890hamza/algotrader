"""ES 1-minute history for the Lab.

Two kinds of yearly files in ``data/es_m1``:

* ``ES_YYYY.npz``   the long history (2008 - Oct 2026)
* ``FEED_YYYY.npz`` bars from your own MT5 feed, topped up every cycle

``load`` splices them: the long history, then feed bars after its last bar. Every file holds
``t`` (epoch ms, int64), ``o h l c`` (float32) and, when known, ``tick_volume``/``real_volume``.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np

FIELDS = ("t", "o", "h", "l", "c")
MINUTE_MS = 60_000


def _year_of(ms: np.ndarray) -> np.ndarray:
    return (ms // 1000).astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970


def _read(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def _concat(parts: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not parts:
        return {"t": np.zeros(0, np.int64), **{k: np.zeros(0, np.float32) for k in "ohlc"}}
    keys = set(FIELDS).intersection(*[p.keys() for p in parts])
    return {k: np.concatenate([p[k] for p in parts]) for k in keys}


def load(data_dir: Path, start_year: int | None = None, end_year: int | None = None) -> dict[str, np.ndarray]:
    """All bars (history + feed) between the years, sorted, without duplicates."""
    def in_range(p: Path) -> bool:
        y = int(p.stem.split("_")[1])
        return (start_year is None or y >= start_year) and (end_year is None or y <= end_year)

    hist = _concat([_read(p) for p in sorted(data_dir.glob("ES_*.npz")) if in_range(p)])
    feed = _concat([_read(p) for p in sorted(data_dir.glob("FEED_*.npz")) if in_range(p)])
    last = hist["t"][-1] if len(hist["t"]) else -1
    keep = feed["t"] > last
    out = {k: np.concatenate([hist[k], feed[k][keep]]) for k in FIELDS}
    order = np.argsort(out["t"], kind="stable")
    out = {k: v[order] for k, v in out.items()}
    uniq = np.r_[True, out["t"][1:] != out["t"][:-1]]
    return {k: v[uniq] for k, v in out.items()}


def last_bar_ms(data_dir: Path) -> int | None:
    """Time of the newest bar on disk (history or feed)."""
    newest = None
    for p in data_dir.glob("*.npz"):
        with np.load(p) as z:
            if len(z["t"]):
                v = int(z["t"][-1])
                newest = v if newest is None else max(newest, v)
    return newest


def append_feed(data_dir: Path, bars: list[dict]) -> int:
    """Add bars from the feed (data-accessor candle dicts) to FEED_YYYY.npz; returns how many were new."""
    if not bars:
        return 0
    t = np.array([int(b["timestamp_ms"]) for b in bars], np.int64)
    new = {"t": t, **{k: np.array([float(b[name]) for b in bars], np.float32) for k, name in zip("ohlc", ("open", "high", "low", "close"))}}
    added = 0
    for y in np.unique(_year_of(t)):
        sel = _year_of(t) == y
        path = data_dir / f"FEED_{y}.npz"
        cur = _read(path) if path.exists() else {k: new[k][:0] for k in FIELDS}
        seen = set(cur["t"].tolist())
        fresh = sel & ~np.isin(t, cur["t"])
        added += int(fresh.sum())
        merged = {k: np.concatenate([cur[k], new[k][fresh]]) for k in FIELDS}
        order = np.argsort(merged["t"], kind="stable")
        tmp = path.with_name(path.stem + ".tmp.npz")
        np.savez_compressed(tmp, **{k: v[order] for k, v in merged.items()})
        tmp.replace(path)
        del seen
    return added


def fetch_feed(feed_url: str, symbol: str, start_ms: int, end_ms: int, timeout: float = 30.0) -> list[dict]:
    """1-minute candles from the data-accessor (your MT5 feed)."""
    url = f"{feed_url}/candles/{symbol}?timeframe=M1&start_ms={start_ms}&end_ms={end_ms}&limit=100000"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data if isinstance(data, list) else []


def coverage(data_dir: Path) -> dict:
    """Bars and missing weekdays per year, for the data report."""
    report = {}
    for p in sorted(data_dir.glob("*.npz")):
        with np.load(p) as z:
            t = z["t"]
        if not len(t):
            continue
        days = np.unique((t // 86_400_000))
        weekdays = (days + 3) % 7 < 5  # 1970-01-01 was a Thursday
        report[p.stem] = {"bars": int(len(t)), "first": int(t[0]), "last": int(t[-1]), "trading_days": int(weekdays.sum())}
    return report
