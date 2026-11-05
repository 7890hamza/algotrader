import unittest
from datetime import datetime, timedelta

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.aln_sdev import OUTPUTS as ALN_OUTPUTS
from indicator_engine.indicators.mtf_sdev import COL, mtf_sdev, parse_show
from indicator_engine.indicators.session_sdev import session_levels
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
LA = ZoneInfo("America/Los_Angeles")


def hourly(start: datetime, hours: int, price=lambda i: 100.0):
    """Hourly bars from `start`, skipping 17:00 New York (the CME break) and Saturdays."""
    t, o, h, lo, c = [], [], [], [], []
    cur, i = start, 0
    while len(t) < hours:
        ny = cur.astimezone(NY)
        if ny.hour != 17 and not (ny.weekday() == 5 or (ny.weekday() == 4 and ny.hour >= 17) or (ny.weekday() == 6 and ny.hour < 18)):
            p = price(i)
            t.append(int(cur.timestamp() * 1000))
            o.append(p)
            c.append(p + (1 if i % 2 else -1))
            h.append(p + 2)
            lo.append(p - 2)
            i += 1
        cur += timedelta(hours=1)
    return (np.array(t, dtype=np.int64), *(np.array(x, dtype=float) for x in (o, h, lo, c)))


class AlnSdevTests(unittest.TestCase):
    def test_am_and_cme_sessions_match_the_existing_sdev_indicators(self) -> None:
        reg = get_registry()
        spec = reg.get("aln_sdev").spec
        self.assertEqual(spec.parameters["sessions"]["default"], "cme, asia, ldn, am, pm")
        self.assertIn("am_+0.5", ALN_OUTPUTS)
        t, o, h, lo, c = hourly(datetime(2026, 8, 2, 18, tzinfo=NY), 24 * 50, lambda i: 100 + (i % 7))
        am = session_levels(t, o, c, session_start="05:00", session_end="09:00", levels=(0.5, 1, 1.5))
        mine = session_levels(t, o, c, session_start="05:00", session_end="09:00", time_zone="America/Los_Angeles",
                              session_days="Mon-Fri", levels=(0.5, 1, 1.5))
        np.testing.assert_array_equal(np.nan_to_num(am), np.nan_to_num(mine))

    def test_warmup_scales_with_bar_length(self) -> None:
        spec = get_registry().get("aln_sdev").spec
        self.assertEqual(spec.warmup({"_bar_minutes": 5}) * 5, spec.warmup({}))


class MtfSdevTests(unittest.TestCase):
    def test_daily_levels_prior_day_and_range(self) -> None:
        t, o, h, lo, c = hourly(datetime(2026, 7, 5, 18, tzinfo=NY), 23 * 40, lambda i: 100 + (i % 5))
        out = mtf_sdev(t, o, h, lo, c, show="d, prior, range", levels=(0.5, 1.0), lookback=5)
        last = len(t) - 1
        d_open = out[last, COL["d_open"]]
        self.assertTrue(np.isfinite(d_open))
        self.assertGreater(out[last, COL["d_+1"]], out[last, COL["d_+0.5"]])
        self.assertAlmostEqual(out[last, COL["d_+1"]] - d_open, d_open - out[last, COL["d_-1"]])
        self.assertTrue(np.isnan(out[last, COL["d_+1.5"]]))  # not in levels
        self.assertTrue(np.isnan(out[last, COL["w_open"]]))  # weekly off
        self.assertEqual(out[last, COL["pdh"]], 106)  # prices 100-104, highs +2
        self.assertEqual(out[last, COL["pdl"]], 98)
        self.assertEqual(out[last, COL["dr_h"]], 106)
        self.assertAlmostEqual(out[last, COL["dr_mid"]], (out[last, COL["dr_h"]] + out[last, COL["dr_l"]]) / 2)
        self.assertAlmostEqual(out[last, COL["adr"]], 8.0)

    def test_sunday_evening_opens_the_new_week(self) -> None:
        t, o, h, lo, c = hourly(datetime(2026, 7, 5, 18, tzinfo=NY), 23 * 120, lambda i: 100 + (i % 3))
        out = mtf_sdev(t, o, h, lo, c, show="w", lookback=4)
        sunday = int(datetime(2026, 9, 27, 18, tzinfo=NY).timestamp() * 1000)
        k = int(np.flatnonzero(t == sunday)[0])
        self.assertEqual(out[k, COL["w_open"]], o[k])
        self.assertNotEqual(out[k - 1, COL["w_open"]], o[k])

    def test_parts_and_warmup(self) -> None:
        self.assertEqual(parse_show("D, w"), {"d", "w"})
        with self.assertRaises(ValueError):
            parse_show("d, year")
        spec = get_registry().get("mtf_sdev").spec
        self.assertGreater(spec.warmup({}), spec.warmup({"show": "d"}))
        self.assertLess(spec.warmup({"_bar_minutes": 15}), spec.warmup({"_bar_minutes": 1}))


if __name__ == "__main__":
    unittest.main()
