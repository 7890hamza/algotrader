import unittest
from datetime import datetime, timedelta

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.aln_tbr import FIELDS, ZONE_STATS, parse_sessions, session_fade
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def asia_nights(count: int, last_path):
    """20:00-02:00 New York 1-minute bars for `count` weeknights; the last follows last_path."""
    times, o, h, low, c = [], [], [], [], []
    day, made = datetime(2026, 8, 31), 0  # a Monday
    rng = np.random.default_rng(5)
    while made < count:
        if day.weekday() < 4 or day.weekday() == 6:  # Sun-Thu evenings
            start = datetime(day.year, day.month, day.day, 20, 0, tzinfo=NY)
            drift = rng.normal(0, 0.3)
            for i in range(360):
                if made == count - 1:
                    p0, p1 = last_path(i), last_path(i + 1)
                else:
                    p0 = 7000 * (1 + drift / 100 * i / 360)
                    p1 = 7000 * (1 + drift / 100 * (i + 1) / 360)
                times.append(int((start + timedelta(minutes=i)).timestamp() * 1000))
                o.append(p0)
                c.append(p1)
                h.append(max(p0, p1))
                low.append(min(p0, p1))
            made += 1
        day += timedelta(days=1)
    return [np.array(x) for x in (times, o, h, low, c)]


class AlnTbrTests(unittest.TestCase):
    def test_asia_session_crosses_midnight(self) -> None:
        def path(i: int) -> float:  # down 15 by 20:15, back to the open by 21:00
            return 7000 - i if i <= 15 else min(7000.0, 6985 + (i - 15) * 0.4)

        t, o, h, low, c = asia_nights(21, path)
        out = session_fade(t, o, h, low, c, "asia")
        last = out[20 * 360 : 21 * 360]
        self.assertTrue(np.isfinite(last[:, 0]).all())  # one session through midnight
        self.assertEqual(last[0, 0], 7000)
        self.assertTrue(np.isnan(out[: 20 * 360, 0]).all())  # not enough history before
        pts = (last[0, 1] - last[0, 0]) / 0.25
        col = FIELDS.index("stretch_near")
        hit = int(np.argmax(np.isfinite(last[:, col])))
        self.assertAlmostEqual(last[hit, col], 7000 - ZONE_STATS["asia"]["stretch"][0] * pts)
        follow = last[hit, FIELDS.index("follow_near")]
        self.assertGreater(follow, 7000)  # after a -0.25 touch the follow-through zone is above
        revert = FIELDS.index("revert_at")
        self.assertTrue(np.isfinite(last[-1, revert]))

    def test_parse_and_registry(self) -> None:
        self.assertEqual(parse_sessions("Asia, LDN,am"), ["asia", "ldn", "am"])
        with self.assertRaises(ValueError):
            parse_sessions("tokyo")
        self.assertIn("aln_tbr", get_registry().list_specs())


if __name__ == "__main__":
    unittest.main()
