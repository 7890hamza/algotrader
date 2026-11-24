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
    # once price is above 505 the old call wall is no longer "above price"
    v = w.find_walls(chain(), 506)
    assert v.call == 510 and v.put == 495  # the put wall below stays the biggest put strike below price


def test_expirations_today_and_friday():
    exps = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-12-04"]
    assert w.expirations(exps, date(2026, 11, 23)) == ["2026-11-23", "2026-11-27"]  # Monday
    assert w.expirations(exps, date(2026, 11, 27)) == ["2026-11-27"]  # Friday: same day
    assert w.expirations(exps, date(2026, 11, 28)) == ["2026-12-04"]  # Saturday: next one
