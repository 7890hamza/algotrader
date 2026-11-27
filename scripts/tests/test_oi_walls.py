"""Checks for the QQQ / SPY wall levels (made-up chains, no internet)."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("oi_walls", Path(__file__).resolve().parents[1] / "oi_walls.py")
w = importlib.util.module_from_spec(spec)
sys.modules["oi_walls"] = w
spec.loader.exec_module(w)
S = w.Strike


def chain():
    # price 500: calls pile up at 505 (biggest) and 510, puts at 495 (biggest) and 490
    return [
        S(488, 100, 3000), S(490, 200, 9000), S(492, 300, 2000), S(495, 400, 12000),
        S(498, 1500, 4000), S(500, 4000, 3500), S(502, 5000, 900), S(505, 15000, 300),
        S(508, 2000, 100), S(510, 11000, 50), S(512, 500, 10),
    ]


def test_walls_follow_the_sts_steps():
    v = w.find_walls(chain(), 500.5)
    assert (v.call, v.outer_call) == (505, 510)
    assert (v.put, v.outer_put) == (495, 490)
    assert 495 < v.flip < 505  # puts dominate below it, calls above


def test_walls_step_when_price_moves():
    # once price is above 505 the old call wall is no longer "above price": the two biggest call
    # strikes left above are 510 and 508, so 508 (nearer) is the inner wall and 510 the outer one
    v = w.find_walls(chain(), 506)
    assert (v.call, v.outer_call) == (508, 510)
    assert v.put == 495  # the put wall below stays the biggest put strike below price


def test_inner_is_the_nearer_of_the_two_biggest():
    s = [S(510, 20000, 0), S(505, 9000, 0), S(495, 0, 7000), S(490, 0, 15000)]
    v = w.find_walls(s, 500)
    assert (v.call, v.outer_call) == (505, 510)  # 510 is bigger, but 505 is nearer: inner
    assert (v.put, v.outer_put) == (495, 490)


def test_daily_pin_is_the_biggest_strike_expiring_today():
    today = [S(500, 3000, 2500), S(505, 4000, 100), S(495, 100, 3000)]
    assert w.daily_pin(today) == 500  # 5,500 contracts, the most of any strike today
    assert w.daily_pin([]) is None


def test_every_refresh_is_archived(tmp_path):
    w.SAVE = tmp_path
    snap = {"t": 1795800000000, "etf": "QQQ", "etfPrice": 600.0, "futPrice": 24600.0, "futSource": "app", "ratio": 41.0,
            "liveRatio": 41.0, "outerCall": 24805.0, "call": 24700.0, "flip": 24590.0, "put": 24495.0, "outerPut": 24395.0,
            "pin": 24600.0, "regime": "positive", "expirations": ["2026-11-27"],
            "etfLevels": {"outerCall": 605, "call": 602.5, "flip": 599.75, "put": 597.5, "outerPut": 595, "pin": 600},
            "_raw": [[600.0, 3000.0, 2500.0, "2026-11-27"]]}
    w.archive("NQ", snap)
    w.archive("NQ", dict(snap, _raw=[]))
    lines = (tmp_path / "levels_NQ.csv").read_text().splitlines()
    assert lines[0].startswith("time_utc,time_pt,etf") and len(lines) == 3
    assert "24700.0" in lines[1] and "positive" in lines[1]
    raw = list((tmp_path / "raw").rglob("*.json.gz"))
    assert len(raw) == 1 and raw[0].name.endswith("_QQQ.json.gz")


def test_expirations_today_and_friday():
    exps = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-12-04"]
    assert w.expirations(exps, date(2026, 11, 23)) == ["2026-11-23", "2026-11-27"]  # Monday
    assert w.expirations(exps, date(2026, 11, 27)) == ["2026-11-27"]  # Friday: same day
    assert w.expirations(exps, date(2026, 11, 28)) == ["2026-12-04"]  # Saturday: next one
