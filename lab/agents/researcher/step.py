"""Researcher, step 1 of the build: keep the data current and report on it.
(Idea testing arrives with the simulator in step 2 and the loop in step 3.)"""

from __future__ import annotations

import time

from labkit import data
from labkit.files import ensure_file, now_iso, write_json

DAY_MS = 86_400_000
CHUNK_MS = 5 * DAY_MS


def run(ctx) -> str:
    cfg = ctx.config
    ensure_file(ctx.memory / "lessons.md", "# Lessons\n\nWhat the Researcher has learned, newest first.\n")
    ensure_file(ctx.memory / "ideas_queue.csv", "id,rule,source,added\n")
    ensure_file(ctx.memory / "tried.csv", "id,rule,trades,win_rate,avg_r,years_positive,verdict,tested\n")

    # Top up from the feed, a few days at a time, from the newest bar on disk.
    added, note = 0, ""
    last = data.last_bar_ms(ctx.data)
    now = int(time.time() * 1000)
    start = (last + 60_000) if last else now - 30 * DAY_MS
    try:
        while start < now:
            end = min(start + CHUNK_MS, now)
            added += data.append_feed(ctx.data, data.fetch_feed(cfg["feed_url"], cfg.get("symbol", "ES"), start, end))
            start = end
    except Exception as e:  # feed down or stack not up: keep going with what's on disk
        note = f" (feed not reachable: {type(e).__name__})"

    cov = data.coverage(ctx.data)
    write_json(ctx.memory / "data_report.json", {"checked": now_iso(), "files": cov, "feed_bars_added": added})
    years = sorted({k.split("_")[1] for k in cov})
    newest = data.last_bar_ms(ctx.data)
    age_min = round((now - newest) / 60_000) if newest else None
    return f"data {years[0] if years else '-'}-{years[-1] if years else '-'}, +{added} feed bars, newest bar {age_min} min old{note}"
