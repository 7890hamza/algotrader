import unittest
from datetime import datetime, timedelta

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.current_day_ohl import current_day_ohl
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def bars(start: datetime, minutes: int):
    times = np.array(
        [int((start + timedelta(minutes=i)).timestamp() * 1000) for i in range(minutes)],
        dtype=np.int64,
    )
    price = 100.0 + np.sin(np.arange(minutes) / 30.0) * 5
    return times, price, price + 0.25, price - 0.25


class CurrentDayOhlTests(unittest.TestCase):
    def test_cme_day_resets_at_3pm_pacific(self) -> None:
        # Monday 13:00 -> Tuesday 16:00 Pacific, 1-minute bars.
        times, open_, high, low = bars(datetime(2026, 10, 19, 13, 0, tzinfo=PACIFIC), 27 * 60)
        out = current_day_ohl(times, open_, high, low)
        # 13:00-13:59 is the end of Monday's CME day; its open is the first bar we have.
        self.assertEqual(out[0, 0], open_[0])
        # 14:00-14:59 is the daily break: nothing drawn.
        self.assertTrue(np.isnan(out[60:120]).all())
        new_day = 120  # 15:00 Monday starts Tuesday's session
        self.assertEqual(out[new_day, 0], open_[new_day])
        self.assertEqual(out[new_day + 500, 1], high[new_day : new_day + 501].max())
        self.assertEqual(out[new_day + 500, 2], low[new_day : new_day + 501].min())
        # The open stays fixed for the whole session.
        self.assertTrue(np.all(out[new_day : new_day + 23 * 60, 0] == open_[new_day]))
        # High never goes down and low never goes up inside a session.
        session = out[new_day : new_day + 23 * 60]
        self.assertTrue(np.all(np.diff(session[:, 1]) >= 0))
        self.assertTrue(np.all(np.diff(session[:, 2]) <= 0))

    def test_regular_hours_session(self) -> None:
        times, open_, high, low = bars(datetime(2026, 10, 20, 5, 0, tzinfo=PACIFIC), 10 * 60)
        out = current_day_ohl(times, open_, high, low, session_start="06:30", session_end="13:00")
        self.assertTrue(np.isnan(out[:90]).all())  # before 06:30
        self.assertEqual(out[90, 0], open_[90])
        self.assertTrue(np.isnan(out[480:]).all())  # from 13:00

    def test_registered(self) -> None:
        self.assertIn("current_day_ohl", get_registry().list_specs())


if __name__ == "__main__":
    unittest.main()
