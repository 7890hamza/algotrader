import unittest
from datetime import datetime

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.hour_stats import COL, hour_stats
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
START = int(datetime(2026, 10, 22, 8, 0, tzinfo=NY).timestamp() * 1000)


def minutes(rows):
    """rows: (minute offset from 08:00 New York, open, high, low, close)."""
    ms = np.array([START + m * 60_000 for m, *_ in rows], dtype=np.int64)
    o, h, lo, c = (np.array(x, dtype=float) for x in list(zip(*rows))[1:])
    return ms, o, h, lo, c


class HourStatsTests(unittest.TestCase):
    def test_breach_of_prior_high_then_back_to_open(self) -> None:
        rows = [(-60 + i, 100, 102, 98, 100) for i in range(60)]  # 7:00 hour: 98-102
        rows += [
            (0, 100, 101, 99.5, 100.5),
            (25, 100.5, 102.25, 100, 102),
            (30, 102, 102, 99.75, 100),
            (45, 100, 100.5, 99, 99),
        ]
        out = hour_stats(*minutes(rows))
        k = 60
        self.assertEqual(out[k, COL["open"]], 100)
        self.assertEqual(out[k, COL["ph"]], 102)
        self.assertEqual(out[k, COL["setup"]], 1)
        self.assertTrue(np.isnan(out[k, COL["side"]]))
        self.assertEqual(out[k + 1, COL["side"]], 1)
        self.assertEqual(out[k + 1, COL["seg"]], 1)  # minute 25
        self.assertGreater(out[k + 1, COL["stretch_far"]], out[k + 1, COL["stretch_near"]])
        self.assertLess(out[k + 1, COL["follow_near"]], 100)
        self.assertTrue(np.isnan(out[k + 1, COL["revert_at"]]))
        self.assertEqual(out[k + 2, COL["revert_at"]], START + 30 * 60_000)
        self.assertTrue(np.isnan(out[0, COL["open"]]))  # 7:00 hour is not drawn

    def test_open_outside_prior_range_is_not_a_setup(self) -> None:
        rows = [(-60 + i, 100, 101, 99, 100) for i in range(60)]
        rows += [(0, 101.5, 103, 101, 102), (10, 102, 104, 101, 103)]
        out = hour_stats(*minutes(rows))
        self.assertEqual(out[60, COL["setup"]], 0)
        self.assertTrue(np.isnan(out[61, COL["side"]]))

    def test_registered(self) -> None:
        self.assertIn("hour_stats", get_registry().list_specs())


if __name__ == "__main__":
    unittest.main()
