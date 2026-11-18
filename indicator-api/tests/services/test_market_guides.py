"""Each chart symbol gets its own index's stats.

ES for ES / MES / SP500, NQ for NQ / MNQ / XYZ100.
"""

import unittest

from app import get_indicator_metadata, nq_stats
from app.game_plan import stats_for
from app.ui_metadata import ALN_STATS, BREAK_RATES, TBR_RATES

AM_TBR, ALN, ALN_TBR, HOUR_STATS, BREAKS = 10, 8, 11, 13, 14


class MarketGuideTests(unittest.TestCase):
    def test_es_family_keeps_the_es_tables(self) -> None:
        for symbol in ("ES", "MES", "SP500"):
            guide = get_indicator_metadata(AM_TBR, symbol)["guide"]
            self.assertEqual(guide["rates"], TBR_RATES["am"])
            self.assertEqual(guide["market"]["family"], "ES")
        self.assertEqual(get_indicator_metadata(BREAKS, "MES")["guide"]["rates"], BREAK_RATES)
        self.assertEqual(get_indicator_metadata(ALN, "ES")["guide"]["source"], "ES 2016-2025")

    def test_nq_family_gets_the_nq_tables(self) -> None:
        for symbol in ("NQ", "MNQ", "XYZ100"):
            meta = get_indicator_metadata(AM_TBR, symbol)
            self.assertEqual(meta["guide"]["rates"], nq_stats.TBR_RATES["am"])
            self.assertTrue(meta["guide"]["source"].startswith("NQ 2016-2025"))
        aln = get_indicator_metadata(ALN, "MNQ")["guide"]
        self.assertEqual(aln["stats"], nq_stats.ALN_STATS)
        self.assertNotEqual(aln["stats"], ALN_STATS)
        self.assertEqual(aln["source"], "NQ 2016-2025 (used for MNQ)")
        sessions = get_indicator_metadata(ALN_TBR, "NQ")["guide"]["sessions"]
        self.assertEqual(
            [s["rates"] for s in sessions], [nq_stats.TBR_RATES[s["key"]] for s in sessions]
        )
        hours = get_indicator_metadata(HOUR_STATS, "XYZ100")["guide"]
        self.assertEqual(hours["hours"], nq_stats.HOUR_RATES)
        self.assertEqual(hours["market"]["venue"], "HYPERLIQUID")

    def test_market_details(self) -> None:
        market = get_indicator_metadata(BREAKS, "MNQ")["guide"]["market"]
        self.assertEqual(
            (market["symbol"], market["tick"], market["pointValue"]), ("MNQ", 0.25, 2.0)
        )

    def test_game_plan_tables_and_tick(self) -> None:
        self.assertEqual(stats_for("MNQ").HOUR_SWEEP, nq_stats.HOUR_SWEEP)
        self.assertEqual(stats_for("ES").family, "ES")
        self.assertEqual(stats_for("ES").TICK, 0.25)
        import numpy as np

        rows = np.array([[0, 6800.0, 6801.0, 6799.0, 6800.5]])
        self.assertAlmostEqual(stats_for("SP500", rows).TICK, 0.1)


if __name__ == "__main__":
    unittest.main()
