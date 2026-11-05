import unittest
from datetime import datetime

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.breaks import COL, breaks, parse_show
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


def rth_day(y, mo, d, path, step=5):
    """5-minute bars 09:30-15:55 New York; path(i) -> (open, high, low, close)."""
    rows = []
    for i in range(78):
        t = ms(y, mo, d, 9, 30) + i * step * 60_000
        rows.append((t, *path(i)))
    return rows


def arrays(rows):
    rows = sorted(rows)
    t = np.array([r[0] for r in rows], dtype=np.int64)
    o, h, lo, c = (np.array([r[k] for r in rows], dtype=float) for k in (1, 2, 3, 4))
    return t, o, h, lo, c


def flat(price, rng=1.0):
    return lambda i: (price, price + rng, price - rng, price)


class BreaksTests(unittest.TestCase):
    def test_inside_day_lower_third_and_prior_low_hit(self) -> None:
        # Monday 100-110 (box 99-111 with wicks); Tuesday opens at 101 then drops to 98.
        mon = rth_day(2026, 10, 5, lambda i: (105, 110, 100, 105))
        tue = rth_day(2026, 10, 6, lambda i: (101, 102, 100.5, 101) if i < 20 else (101, 101, 99.5, 99.5))
        out = breaks(*arrays(mon + tue), show="rth")
        k = 78  # Tuesday 09:30
        self.assertEqual(out[k, COL["prth_h"]], 110)
        self.assertEqual(out[k, COL["prth_l"]], 100)
        self.assertEqual(out[k, COL["rth_setup"]], 0)
        self.assertEqual(out[k, COL["rth_third"]], -1)
        self.assertEqual(out[k, COL["rth_touch_h"]], 1)
        self.assertTrue(np.isnan(out[k + 19, COL["rth_hit_l"]]))  # 100.5 / 100 lows: not 1 tick past
        self.assertEqual(out[k + 20, COL["rth_hit_l"]], ms(2026, 10, 6, 9, 30) + 20 * 300_000)
        self.assertTrue(np.isnan(out[-1, COL["rth_hit_h"]]))
        self.assertEqual(out[0, COL["rth_box_h"]], 110)  # Monday is Tuesday's "yesterday": boxed
        self.assertTrue(np.isnan(out[k, COL["rth_box_h"]]))  # today: no box until tomorrow starts
        self.assertTrue(np.isnan(out[0, COL["prth_h"]]))  # no Friday before it

    def test_gap_up_turns_off_the_high_touch(self) -> None:
        mon = rth_day(2026, 10, 5, flat(105, 5))
        tue = rth_day(2026, 10, 6, flat(115, 1))
        out = breaks(*arrays(mon + tue), show="rth")
        self.assertEqual(out[78, COL["rth_setup"]], 1)
        self.assertEqual(out[78, COL["rth_touch_h"]], 0)
        self.assertEqual(out[78, COL["rth_touch_l"]], 1)
        self.assertTrue(np.isnan(out[78, COL["rth_third"]]))

    def test_ib_levels_side_hits_and_targets(self) -> None:
        def path(i):
            if i < 12:  # IB 100-110, closes at 108 (above the 105 mid)
                return (104, 110 if i == 3 else 106, 100 if i == 5 else 103, 108 if i == 11 else 105)
            if i < 30:
                return (108, 109, 106, 108)
            return (108, 112, 107, 111)
        rows = rth_day(2026, 10, 6, path)
        out = breaks(*arrays(rows), show="ib, targets")
        self.assertEqual(out[0, COL["ib_box_h"]], 106)  # running box
        self.assertEqual(out[11, COL["ib_box_h"]], 110)
        self.assertTrue(np.isnan(out[11, COL["ib_h"]]))
        self.assertEqual(out[12, COL["ib_h"]], 110)
        self.assertEqual(out[12, COL["ib_mid"]], 105)
        self.assertEqual(out[12, COL["ib_side"]], 1)
        self.assertEqual(out[12, COL["ib_valid"]], 1)
        self.assertTrue(np.isnan(out[29, COL["ib_hit_h"]]))
        self.assertEqual(out[30, COL["ib_hit_h"]], ms(2026, 10, 6, 12, 0))
        self.assertAlmostEqual(out[30, COL["ib_ext_med"]], 110 + 0.62 * 10)
        self.assertAlmostEqual(out[30, COL["ib_ext_p75"]], 110 + 1.18 * 10)
        self.assertTrue(np.isnan(out[29, COL["ib_ext_med"]]))

    def test_eth_prior_session_levels(self) -> None:
        # Hourly bars Sunday 18:00 -> Monday 16:00 (ETH Mon), then Monday 18:00 -> Tuesday 10:00.
        rows = []
        for h in range(23):
            t = ms(2026, 10, 4, 18, 0) + h * 3_600_000
            rows.append((t, 100, 104, 96, 100))
        for h in range(17):
            t = ms(2026, 10, 5, 18, 0) + h * 3_600_000
            rows.append((t, 103, 105 if h == 10 else 103.5, 102, 103))
        out = breaks(*arrays(rows), show="eth")
        k = 23
        self.assertEqual(out[k, COL["peth_h"]], 104)
        self.assertEqual(out[k, COL["peth_l"]], 96)
        self.assertEqual(out[k, COL["eth_setup"]], 0)
        self.assertEqual(out[k, COL["eth_third"]], 1)
        self.assertEqual(out[k + 10, COL["eth_hit_h"]], ms(2026, 10, 5, 18, 0) + 10 * 3_600_000)
        self.assertTrue(np.isnan(out[k, COL["prth_h"]]))

    def test_retracement_starts_from_the_ib_leg(self) -> None:
        # IB 100-110, low first (bar 1) then high (bar 3) = up leg 100 -> 110, zone 106-104.
        # Dip to 105 touches it, close back above 106 = Out; new high 112 = win and a new leg
        # 105 -> 112; then a drop below 105 (past 100%) flips the trend.
        def path(i):
            if i < 12:
                return (105, 110 if i == 3 else 107, 100 if i == 1 else 104, 105)
            seq = {12: (108, 108, 105, 105.5), 13: (105.5, 107, 105.5, 106.5), 14: (106.5, 112, 106, 111),
                   15: (111, 111, 104, 104)}
            return seq.get(i, (104, 104.5, 103.5, 104))
        out = breaks(*arrays(rth_day(2026, 10, 6, path)), show="ib, retrace")
        self.assertTrue(np.isnan(out[11, COL["rt_dir"]]))  # still inside the IB window
        self.assertEqual(out[12, COL["rt_dir"]], 1)
        self.assertEqual(out[12, COL["rt_start"]], 100)
        self.assertEqual(out[12, COL["rt_end"]], 110)
        self.assertEqual(out[12, COL["rt_start_at"]], ms(2026, 10, 6, 9, 35))
        self.assertTrue(np.isnan(out[12, COL["rt_out_at"]]))  # touching bar is not the Out
        self.assertEqual(out[13, COL["rt_out_px"]], 106.5)
        self.assertEqual(out[13, COL["rt_res"]], 1)  # filled in once the new high came
        self.assertEqual(out[14, COL["rt_start"]], 105)
        self.assertEqual(out[14, COL["rt_zone"]], 1)
        self.assertEqual(out[15, COL["rt_dir"]], -1)
        self.assertEqual(out[15, COL["rt_start"]], 112)

    def test_ib_high_first_is_a_down_leg(self) -> None:
        def path(i):
            if i < 12:
                return (105, 110 if i == 2 else 107, 100 if i == 9 else 104, 105)
            return (102, 103, 101, 102)
        out = breaks(*arrays(rth_day(2026, 10, 6, path)), show="ib, retrace")
        self.assertEqual(out[12, COL["rt_dir"]], -1)
        self.assertEqual(out[12, COL["rt_start"]], 110)
        self.assertEqual(out[12, COL["rt_end"]], 100)

    def test_parts_and_registry(self) -> None:
        self.assertEqual(parse_show("RTH; ib"), {"rth", "ib"})
        with self.assertRaises(ValueError):
            parse_show("rth, nope")
        spec = get_registry().get("breaks").spec
        self.assertEqual(spec.parameters["show"]["default"], "rth, ib, eth, targets, retrace")


if __name__ == "__main__":
    unittest.main()
