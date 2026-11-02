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

    def test_registered(self) -> None:
        self.assertIn("engulfing", get_registry().list_specs())


if __name__ == "__main__":
    unittest.main()
