import unittest
from datetime import datetime, timedelta

import numpy as np
from indicator_engine.indicators.am_tbr import COL, ZONE_STATS, am_tbr
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def mornings(count: int, last_path):
    """5:00-9:00 Pacific 1-minute bars; flat history days, then one day following last_path."""
    times, o, h, low, c = [], [], [], [], []
    day, made = datetime(2026, 9, 1), 0
    rng = np.random.default_rng(1)
    while made < count:
        if day.weekday() < 5:
            final = made == count - 1
            drift = rng.normal(0, 0.4)
            start = datetime(day.year, day.month, day.day, 5, 0, tzinfo=PACIFIC)
            for i in range(240):
                t = start + timedelta(minutes=i)
                if final:
                    p0, p1 = last_path(i), last_path(i + 1)
                else:
                    p0 = 7000 * (1 + drift / 100 * i / 240)
                    p1 = 7000 * (1 + drift / 100 * (i + 1) / 240)
                times.append(int(t.timestamp() * 1000))
                o.append(p0)
                c.append(p1)
                h.append(max(p0, p1))
                low.append(min(p0, p1))
            made += 1
        day += timedelta(days=1)
    return [np.array(x) for x in (times, o, h, low, c)]


class AmTbrZoneTests(unittest.TestCase):
    def test_touch_revert_and_zones(self) -> None:
        # Last morning: up 20 points by 5:20, back to the open at 6:00, then down.
        def path(i: int) -> float:
            if i <= 20:
                return 7000 + i
            if i <= 60:
                return 7020 - (i - 20) * 0.5
            return 7000 - (i - 60) * 0.1

        t, o, h, low, c = mornings(21, path)
        out = am_tbr(t, o, h, low, c, ddof=1)
        last = slice(20 * 240, 21 * 240)
        rows = out[last]
        base, up = rows[0, COL["open"]], rows[0, COL["+0.25"]]
        self.assertEqual(base, 7000)
        pts = (up - base) / 0.25
        hit = int(np.argmax(rows[:, COL["touch_side"]] == 1))
        self.assertTrue(np.isnan(rows[:hit, COL["touch_side"]]).all())
        self.assertGreaterEqual(h[20 * 240 + hit], up)
        med, p75, p90 = ZONE_STATS[(1, 8)]["stretch"]
        self.assertAlmostEqual(rows[hit, COL["stretch_near"]], base + med * pts)
        self.assertAlmostEqual(rows[hit, COL["stretch_far"]], base + p90 * pts)
        f_med = ZONE_STATS[(1, 8)]["follow"][0]
        self.assertAlmostEqual(rows[hit, COL["follow_near"]], base - f_med * pts)
        back = int(np.argmax(np.isfinite(rows[:, COL["revert_at"]])))
        self.assertEqual(back, 59)  # the 5:59 bar closes at 7000


if __name__ == "__main__":
    unittest.main()
