"""Trader, step 1 of the build: check the market clock and the feed. No trading yet
(forward testing arrives in step 4; demo trading only after your go-ahead)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from labkit.files import ensure_file

PT = ZoneInfo("America/Los_Angeles")


def market_open(now: datetime) -> bool:
    """ES trades Sunday 3 PM - Friday 2 PM Pacific, with a daily break 2-3 PM."""
    wd, minute = now.weekday(), now.hour * 60 + now.minute
    if wd == 5:
        return False
    if wd == 6:
        return minute >= 15 * 60
    if wd == 4 and minute >= 14 * 60:
        return False
    return not (14 * 60 <= minute < 15 * 60)


def run(ctx) -> str:
    ensure_file(ctx.memory / "journal.csv", "card,day,side,entry_time,entry,stop,target,exit_time,exit,result_r,mode\n")
    cards = sorted((ctx.lab / "agents" / "researcher" / "results").glob("card_*.json"))
    now = datetime.now(PT)
    state = "open" if market_open(now) else "closed"
    return f"market {state}; {len(cards)} strategy cards published; forward testing starts in step 4"
