import unittest
from datetime import datetime, timedelta

import numpy as np
from indicator_engine import get_batch_engine, get_registry
from indicator_engine.core.bars import BarTensor
from indicator_engine.core.params import ParamGrid
from indicator_engine.indicators.session_sdev import (
    MULTIPLIERS,
    OUTPUTS,
    CmeOpenSDEV,
    SessionSDEV,
    parse_levels,
    session_levels,
    to_epoch_ms,
)
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def build_sessions(days, *, minutes=240, start=(5, 0), skip=()):
    """1-minute bars from 5:00 Pacific for each (date, open, close) session."""
    times, opens, closes = [], [], []
    for day, open_, close in days:
        base = datetime(day.year, day.month, day.day, *start, tzinfo=PACIFIC)
        for i in range(minutes):
            if i in skip:
                continue
            times.append(_ms(base + timedelta(minutes=i)))
            opens.append(open_ if i == 0 else close)
            closes.append(close)
    return np.array(times, dtype=np.int64), np.array(opens), np.array(closes)


def weekdays(start: datetime, count: int):
    out, day = [], start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


class SessionSdevTests(unittest.TestCase):
    def setUp(self) -> None:
        self.days = weekdays(datetime(2026, 9, 1), 22)
        rng = np.random.default_rng(7)
        self.changes = rng.normal(0, 0.4, size=len(self.days))
        self.sessions = [
            (d, 7000.0 + i, (7000.0 + i) * (1 + c / 100))
            for i, (d, c) in enumerate(zip(self.days, self.changes))
        ]

    def test_levels_use_previous_complete_sessions_only(self) -> None:
        times, opens, closes = build_sessions(self.sessions)
        levels = session_levels(times, opens, closes, lookback=20)
        first_bar_day21 = 20 * 240
        expected_sigma = float(np.std(self.changes[:20], ddof=0))
        open21 = self.sessions[20][1]
        self.assertAlmostEqual(levels[first_bar_day21, 0], open21)
        plus_one = levels[first_bar_day21, OUTPUTS.index("+1")]
        self.assertAlmostEqual(plus_one, open21 * (1 + expected_sigma / 100), places=9)
        minus_two = levels[first_bar_day21, OUTPUTS.index("-2")]
        self.assertAlmostEqual(minus_two, open21 * (1 - 2 * expected_sigma / 100), places=9)
        # Not enough history before day 21: nothing is drawn.
        self.assertTrue(np.isnan(levels[: 20 * 240]).all())
        # Levels stay frozen for the whole session even after its own close.
        self.assertTrue(np.allclose(levels[20 * 240 : 21 * 240, OUTPUTS.index("+1")], plus_one))

    def test_incomplete_session_is_skipped(self) -> None:
        # Day 0 has only 100 minutes, so the first complete 20 are days 1..20.
        times0, opens0, closes0 = build_sessions(self.sessions[:1], minutes=100)
        times1, opens1, closes1 = build_sessions(self.sessions[1:])
        times = np.concatenate([times0, times1])
        levels = session_levels(
            times, np.concatenate([opens0, opens1]), np.concatenate([closes0, closes1])
        )
        day20 = 100 + 19 * 240  # first bar of the 21st session
        self.assertTrue(np.isnan(levels[: day20 + 240]).all())  # only 19 complete before it
        day21 = day20 + 240
        sigma = float(np.std(self.changes[1:21], ddof=0))
        open21 = self.sessions[21][1]
        self.assertAlmostEqual(
            levels[day21, OUTPUTS.index("+1")], open21 * (1 + sigma / 100), places=9
        )

    def test_missing_open_bar_means_no_levels_that_day(self) -> None:
        times, opens, closes = build_sessions(self.sessions, skip=range(0, 6))
        levels = session_levels(times, opens, closes, lookback=20)
        self.assertTrue(np.isnan(levels).all())

    def test_follows_daylight_saving(self) -> None:
        # Sessions around the November DST change still open at 5:00 Pacific.
        days = weekdays(datetime(2026, 10, 1), 24)
        sessions = [(d, 7000.0, 7000.0 * (1 + 0.1 * (i % 3 - 1) / 100)) for i, d in enumerate(days)]
        times, opens, closes = build_sessions(sessions)
        levels = session_levels(times, opens, closes, lookback=20)
        last_day = days[-1]
        five_am = _ms(datetime(last_day.year, last_day.month, last_day.day, 5, 0, tzinfo=PACIFIC))
        idx = int(np.searchsorted(times, five_am))
        self.assertFalse(np.isnan(levels[idx, 0]))
        self.assertTrue(np.isnan(levels[idx - 1, 0]) or levels[idx - 1, 0] == 7000.0)

    def test_registered_and_runs_through_batch_engine(self) -> None:
        times, opens, closes = build_sessions(self.sessions)
        data = np.stack([opens, closes], axis=1)[:, np.newaxis, :]
        bars = BarTensor(
            data=data,
            time=times,
            assets=np.array(["ES"], dtype=object),
            fields=np.array(["open", "close"], dtype=object),
        )
        engine = get_batch_engine(get_registry())
        result = engine.run("session_sdev", bars, ParamGrid({"lookback": [20]}))
        self.assertEqual(result.tensor.data.shape[2], len(OUTPUTS))
        self.assertFalse(np.isnan(result.tensor.data[20 * 240, 0, 0, 0]))

    def test_warmup_covers_lookback_sessions(self) -> None:
        self.assertGreaterEqual(SessionSDEV().spec.warmup({"lookback": 20}), 28 * 1440)

    def test_time_conversion(self) -> None:
        import pandas as pd

        expected = 1792670400000
        stamps = np.array(["2026-10-22T12:00:00"], dtype="datetime64[ns]")
        self.assertEqual(int(to_epoch_ms(stamps)[0]), expected)
        index = pd.DatetimeIndex(["2026-10-22T12:00:00"], tz="UTC")
        for unit in ("s", "ms", "us", "ns"):
            objects = index.as_unit(unit).to_numpy(dtype=object)
            self.assertEqual(int(to_epoch_ms(objects)[0]), expected)


if __name__ == "__main__":
    unittest.main()


class SessionOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.days = weekdays(datetime(2026, 9, 1), 22)
        self.sessions = [(d, 7000.0 + i, 7000.0 + i + (i % 3 - 1)) for i, d in enumerate(self.days)]

    def _with_overnight_bars(self):
        """Session bars plus one bar at 12:00 Pacific on every day."""
        times, opens, closes = build_sessions(self.sessions)
        extra = np.array(
            [_ms(datetime(d.year, d.month, d.day, 12, 0, tzinfo=PACIFIC)) for d in self.days]
        )
        order = np.argsort(np.concatenate([times, extra]))
        all_times = np.concatenate([times, extra])[order]
        all_opens = np.concatenate([opens, np.full(extra.size, 1.0)])[order]
        all_closes = np.concatenate([closes, np.full(extra.size, 1.0)])[order]
        return all_times, all_opens, all_closes

    def test_session_extend_stops_at_session_end(self) -> None:
        times, opens, closes = self._with_overnight_bars()
        noon = _ms(datetime(2026, 9, 30, 12, 0, tzinfo=PACIFIC))
        noon_idx = int(np.searchsorted(times, noon))
        inside = session_levels(times, opens, closes, extend="session")
        carried = session_levels(times, opens, closes, extend="next_session")
        self.assertTrue(np.isnan(inside[noon_idx]).all())
        self.assertFalse(np.isnan(carried[noon_idx, 0]))

    def test_only_selected_levels_are_drawn(self) -> None:
        times, opens, closes = build_sessions(self.sessions)
        levels = session_levels(times, opens, closes, levels=(0.5, 1.0))
        row = levels[21 * 240]
        self.assertFalse(np.isnan(row[OUTPUTS.index("+0.5")]))
        self.assertFalse(np.isnan(row[OUTPUTS.index("-1")]))
        self.assertTrue(np.isnan(row[OUTPUTS.index("+0.25")]))
        self.assertTrue(np.isnan(row[OUTPUTS.index("+2")]))

    def test_parse_levels(self) -> None:
        self.assertEqual(parse_levels("0.25, 0.5,1"), (0.25, 0.5, 1.0))
        self.assertEqual(parse_levels("all"), MULTIPLIERS)
        with self.assertRaises(ValueError):
            parse_levels("0.3")

    def test_cme_sessions_run_sunday_to_thursday(self) -> None:
        start, sessions, day = datetime(2026, 9, 6), [], datetime(2026, 9, 6)
        while len(sessions) < 22:
            if day.weekday() in (6, 0, 1, 2, 3):
                sessions.append((day, 7000.0 + len(sessions), 7001.0 + len(sessions) % 2))
            day += timedelta(days=1)
        self.assertEqual(sessions[0][0], start)  # first session is a Sunday
        times, opens, closes = build_sessions(sessions, start=(15, 0))
        levels = session_levels(
            times, opens, closes, session_start="15:00", session_end="19:00", session_days="Sun-Thu"
        )
        self.assertFalse(np.isnan(levels[20 * 240, 0]))
        weekday_only = session_levels(
            times, opens, closes, session_start="15:00", session_end="19:00", session_days="Mon-Fri"
        )
        self.assertTrue(np.isnan(weekday_only[20 * 240, 0]))  # Sundays dropped, too few

    def test_cme_indicator_defaults(self) -> None:
        spec = CmeOpenSDEV().spec
        self.assertEqual(spec.id, "cme_open_sdev")
        self.assertEqual(spec.parameters["session_start"]["default"], "15:00")
        self.assertEqual(spec.parameters["session_end"]["default"], "19:00")
        self.assertEqual(spec.parameters["session_days"]["default"], "Sun-Thu")
        self.assertTrue(spec.sparse_outputs)
        self.assertIn("cme_open_sdev", get_registry().list_specs())
