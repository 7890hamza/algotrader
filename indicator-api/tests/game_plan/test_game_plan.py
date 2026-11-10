import json
import unittest
from datetime import date, datetime, timedelta, timezone

import numpy as np
from zoneinfo import ZoneInfo

from app.game_plan import build_plan, day_window, previous_trading_day, trading_day_for

PT = ZoneInfo("America/Los_Angeles")


def ms(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=PT).timestamp() * 1000)


def minute_bars(start, end, path):
    rows, t = [], start
    while t < end:
        local = datetime.fromtimestamp(t / 1000, PT)
        if not (local.hour == 14):  # the CME maintenance hour
            o, h, l, c = path(t)
            rows.append((t, o, h, l, c))
        t += 60_000
    return np.array(rows, dtype=float)


def hourly(m1):
    out = {}
    for t, o, h, l, c in m1:
        k = int(t // 3_600_000 * 3_600_000)
        if k not in out:
            out[k] = [k, o, h, l, c]
        else:
            r = out[k]
            r[2], r[3], r[4] = max(r[2], h), min(r[3], l), c
    return np.array(list(out.values()), dtype=float)


class GamePlanTests(unittest.TestCase):
    def test_trading_day_rolls_at_3pm_and_over_weekends(self) -> None:
        self.assertEqual(trading_day_for(ms(2026, 11, 5, 10)), date(2026, 11, 5))
        self.assertEqual(trading_day_for(ms(2026, 11, 5, 15, 5)), date(2026, 11, 6))
        self.assertEqual(trading_day_for(ms(2026, 11, 6, 16)), date(2026, 11, 9))  # Fri evening -> Mon
        self.assertEqual(previous_trading_day(date(2026, 11, 9)), date(2026, 11, 6))
        s, e = day_window(date(2026, 11, 5))
        self.assertEqual((s, e), (ms(2026, 11, 4, 15), ms(2026, 11, 5, 14)))

    def test_targets_hits_and_carry_over(self) -> None:
        # Mon-Tue flat around 100 with a 98-102 range each day, then Wednesday trends up to 110.
        def path(t):
            if t < ms(2026, 11, 4, 6, 30):
                return 100.0, 101.0, 99.0, 100.0
            k = (t - ms(2026, 11, 4, 6, 30)) / 60_000
            p = min(110.0, 100 + k * 0.05)
            return p, p + 0.25, p - 0.25, p
        m1 = minute_bars(ms(2026, 11, 1, 15), ms(2026, 11, 4, 14), path)
        h1 = np.vstack([hourly(minute_bars(ms(2026, 9, 20, 15), ms(2026, 11, 1, 14), lambda t: (100.0, 101.0, 99.0, 100.0))), hourly(m1)])
        plan = build_plan(m1, h1, date(2026, 11, 4))
        json.dumps(plan)  # serialisable as is
        lv = {x["id"]: x for x in plan["levels"]}
        self.assertEqual(lv["peth_h"]["price"], 101.0)
        self.assertIsNotNone(lv["peth_h"]["hitAt"])  # the trend took yesterday's high
        self.assertIsNone(lv["peth_l"]["hitAt"])
        self.assertEqual(lv["peth_l"]["until"], plan["end"])  # missed targets stay open all day
        self.assertIn("ib_h", lv)
        self.assertLess(lv["ib_h"]["origUntil"], lv["ib_h"]["until"])
        self.assertEqual(plan["last"]["close"], 110.0)
        self.assertEqual(plan["path"][-1][3], 110.0)  # 5-minute [t, high, low, close] for the mini chart
        self.assertEqual(plan["path"][0][0] % 300_000, 0)
        sweeps = [x for x in plan["levels"] if x["kind"] == "hour_open" and not x["never"]]
        self.assertTrue(all(x["frm"] > int(x["id"].split("_")[1]) for x in sweeps))

    def test_yesterdays_untouched_levels_carry_into_today(self) -> None:
        def path(t):
            return 100.0, 101.0, 99.0, 100.0
        m1 = minute_bars(ms(2026, 11, 1, 15), ms(2026, 11, 5, 14), path)
        h1 = np.vstack([hourly(minute_bars(ms(2026, 9, 20, 15), ms(2026, 11, 1, 14), path)), hourly(m1)])
        plan = build_plan(m1, h1, date(2026, 11, 5))
        carried = [x for x in plan["levels"] if x.get("fromDay")]
        self.assertTrue(all(x["fromDay"] == "Wed" and x["odds"] is None for x in carried))
        self.assertTrue(all(x["frm"] == plan["start"] for x in carried))



class RouteRowsTests(unittest.TestCase):
    def test_rows_keep_epoch_ms_whatever_the_index_unit(self) -> None:
        import pandas as pd

        from app.routes.game_plan import _rows

        t = [1793915760000, 1793915820000]
        for unit_index in (pd.to_datetime(t, unit="ms", utc=True), pd.to_datetime(t, unit="ms", utc=True).as_unit("ns")):
            df = pd.DataFrame({"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0]}, index=unit_index)
            self.assertEqual(_rows(df)[:, 0].astype("int64").tolist(), t)


if __name__ == "__main__":
    unittest.main()


class AllIndicatorsTests(unittest.TestCase):
    def test_every_indicator_prints_on_the_plan(self) -> None:
        # Five weeks of a gentle zig-zag (so the TBR SDEVs exist), then Wednesday trends up.
        def path(t):
            k = t // 60_000
            base = 100 + 2 * np.sin(k / 37.0) + (k % 1440) / 1440.0
            if t >= ms(2026, 11, 4, 6, 30):
                base += min(10.0, (t - ms(2026, 11, 4, 6, 30)) / 60_000 * 0.05)
            return base, base + 0.5, base - 0.5, base + 0.25
        m1 = minute_bars(ms(2026, 9, 27, 15), ms(2026, 11, 4, 14), path)
        h1 = hourly(m1)
        plan = build_plan(m1, h1, date(2026, 11, 4), h1_long=h1)
        groups = {lv["group"] for lv in plan["levels"]}
        for g in ("AMTB", "TBR", "MTF D", "Opens", "ALN", "IB retrace", "SDEV", "Hour", "Hour zones", "IB"):
            self.assertIn(g, groups)
        self.assertIn(plan["ctx"]["aln"]["pattern"], (1, 2, 3, 4))
        # TBR lines stay in their own session: never carried to the end of the day
        am = next(lv for lv in plan["levels"] if lv["id"] == "tbr_am_+0.25")
        self.assertEqual(am["until"], ms(2026, 11, 4, 9))
        self.assertNotIn("carry", am)
        json.dumps(plan)
