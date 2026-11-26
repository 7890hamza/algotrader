import unittest

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.engulfing import COL, engulfing


def run(bars):
    o, h, lo, c = (np.array(x, dtype=float) for x in zip(*bars))
    return engulfing(np.arange(len(o), dtype=np.int64) * 60_000, o, h, lo, c, window=10)


class EngulfingTests(unittest.TestCase):
    def test_bearish_engulfing_follows_through(self) -> None:
        # green 100->104, red 105->99 covers and is bigger, then price falls
        out = run(
            [(100, 104.5, 99.5, 104), (105, 106, 98, 99), (99, 99.5, 95, 95.5), (95, 96, 90, 91)]
        )
        self.assertEqual(out[1, COL["signal"]], -1)
        self.assertEqual(out[1, COL["body_top"]], 105)
        self.assertEqual(out[1, COL["inval_bear"]], 105)
        self.assertEqual(out[1, COL["outcome"]], 1)  # ran one body (6 pts) before invalidation
        self.assertEqual(out[1, COL["mfe"]], 9)  # 99 -> 90
        self.assertEqual(out[1, COL["mae"]], 0.5)

    def test_wicks_do_not_count_and_bigger_body_required(self) -> None:
        # red body 104->100.5 does not reach the green open 100 -> no signal
        out = run([(100, 104, 99, 104), (104, 108, 95, 100.5)])
        self.assertTrue(np.isnan(out[1, COL["signal"]]))
        # equal body is not bigger
        out = run([(100, 104, 99, 104), (104, 105, 99, 100)])
        self.assertTrue(np.isnan(out[1, COL["signal"]]))

    def test_equal_open_counts_and_close_invalidates(self) -> None:
        # bullish: red 104->100, green opens 100 (equal) closes 105;
        # a later close below 100 invalidates
        out = run(
            [
                (104, 104.5, 99.5, 100),
                (100, 105.5, 99.8, 105),
                (105, 105.2, 99, 101),
                (101, 101, 97, 99),
            ]
        )
        self.assertEqual(out[1, COL["signal"]], 1)
        self.assertEqual(out[1, COL["outcome"]], -1)
        self.assertEqual(out[1, COL["inval_at"]], 3 * 60_000)
        self.assertEqual(out[3, COL["inval_bull"]], 100)  # line ends on the break

    def test_marubozu_open_and_return(self) -> None:
        # green opens at its low 100 (no lower wick), price comes back to 100 on candle 3;
        # red opens at its high 110 (no upper wick) and price never returns
        out = run(
            [
                (100, 103, 100, 102.5),
                (102.5, 104, 101, 103),
                (103, 103.5, 99.75, 101),
                (110, 110, 105, 106),
                (106, 107, 104, 104.5),
            ]
        )
        self.assertEqual(out[0, COL["maru_side"]], 1)
        self.assertEqual(out[0, COL["maru_price"]], 100)
        self.assertEqual(out[0, COL["maru_back_at"]], 2 * 60_000)
        self.assertEqual(out[3, COL["maru_side"]], -1)
        self.assertTrue(np.isnan(out[3, COL["maru_back_at"]]))
        # a lower wick, or a body under 1 point, is not a no-wick candle
        self.assertTrue(np.isnan(out[1, COL["maru_side"]]))
        small = run([(100, 100.75, 100, 100.5)])
        self.assertTrue(np.isnan(small[0, COL["maru_side"]]))

    def test_registered(self) -> None:
        self.assertIn("engulfing", get_registry().list_specs())


if __name__ == "__main__":
    unittest.main()


class HigherTimeframeTests(unittest.TestCase):
    """60-minute engulfings on 1-minute bars, filtered by the 12-hour HL / LH bias."""

    @staticmethod
    def minute_bars(start_iso: str, hourly):
        """Expand hourly (o, h, l, c) into 60 one-minute bars each (straight path o -> c, wicks at the ends)."""
        from datetime import datetime

        t0 = int(datetime.fromisoformat(start_iso).timestamp() * 1000)
        t, o, h, lo, c = [], [], [], [], []
        for k, (ho, hh, hl, hc) in enumerate(hourly):
            path = np.linspace(ho, hc, 61)
            for m in range(60):
                t.append(t0 + (k * 60 + m) * 60_000)
                o.append(path[m]); c.append(path[m + 1])
                h.append(max(path[m], path[m + 1]) + (hh - max(ho, hc) if m == 30 else 0))
                lo.append(min(path[m], path[m + 1]) - (min(ho, hc) - hl if m == 31 else 0))
        return (np.array(t, dtype=np.int64), *(np.array(x, dtype=float) for x in (o, h, lo, c)))

    def test_twelve_hour_tags_bias_and_filter(self) -> None:
        from indicator_engine.indicators.engulfing import engulfing_htf

        # 6 PM New York start (23:00 UTC in November). 12h #1 range 100-110, #2 higher low 104,
        # lower high 109? no: #2 high 115 (HH) low 104 (HL) -> bias up for the next 12 hours.
        night = [(105, 110, 100, 106)] + [(106, 107, 105, 106)] * 11
        day = [(106, 115, 104, 107)] + [(107, 108, 106, 107)] * 11
        # next 12h: a green hour engulfing a red one (bullish), then a bearish engulfing
        nxt = [(108, 108.5, 106.5, 107), (106.8, 110, 106.5, 109.5), (109.6, 109.8, 109, 109.8), (110, 110.2, 106, 106.5)] + [(106.5, 107, 106, 106.6)] * 8
        t, o, h, lo, c = self.minute_bars("2026-11-09T23:00:00+00:00", night + day + nxt)
        out = engulfing_htf(t, o, h, lo, c, window=10)
        third = 24 * 60  # first minute of the third 12-hour candle
        self.assertEqual(out[third, COL["h12_lo_tag"]], 1)  # HL
        self.assertEqual(out[third, COL["h12_hi_tag"]], 1)  # HH
        self.assertEqual(out[third, COL["bias"]], 1)
        self.assertTrue(np.isnan(out[third - 1, COL["bias"]]) or out[third - 1, COL["bias"]] != 1)  # not before it closes
        sig_rows = np.flatnonzero(~np.isnan(out[:, COL["signal"]]))
        self.assertEqual(len(sig_rows), 1)
        self.assertEqual(out[sig_rows[0], COL["signal"]], 1)  # the bullish one, with the bias
        self.assertEqual(sig_rows[0], third + 2 * 60 - 1)  # on the last minute of that hour
        against = np.flatnonzero(~np.isnan(out[:, COL["against"]]))
        self.assertEqual(out[against[-1], COL["against"]], -1)  # the bearish one is hidden

    def test_chart_timeframe_mode_matches_old_behaviour(self) -> None:
        from indicator_engine.indicators.engulfing import engulfing_htf

        bars = [(100, 104.5, 99.5, 104), (105, 106, 98, 99), (99, 99.5, 95, 95.5)]
        o, h, lo, c = (np.array(x, dtype=float) for x in zip(*bars))
        t = np.arange(3, dtype=np.int64) * 60_000
        old = engulfing(t, o, h, lo, c, window=10)
        new = engulfing_htf(t, o, h, lo, c, window=10, tf_minutes=0, bias="none")
        np.testing.assert_array_equal(np.isnan(old[:, :12]), np.isnan(new[:, :12]))
