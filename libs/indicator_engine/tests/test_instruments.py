"""Instrument awareness: ES / MES / NQ / MNQ and Hyperliquid SP500 / XYZ100."""

import unittest
from datetime import datetime, timezone

import numpy as np
from indicator_engine.core.bars import BarTensor
from indicator_engine.indicators.am_tbr import ZONE_STATS, ZONE_STATS_NQ, AmTBR
from indicator_engine.indicators.breaks import COL as BC
from indicator_engine.indicators.breaks import Breaks, breaks
from indicator_engine.indicators.hour_stats import HourStats
from indicator_engine.instruments import (
    cme_open,
    family_for,
    instrument_for,
    root_symbol,
    session_rows,
)


def _ms(*args) -> int:
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


class InstrumentLookupTests(unittest.TestCase):
    def test_families(self) -> None:
        for s in ("ES", "MES", "@EP", "ESZ6", "MESH27", "ES 12-26", "SP500", "xyz:SP500", "US500"):
            self.assertEqual(family_for(s), "ES", s)
        for s in (
            "NQ",
            "MNQ",
            "@ENQ",
            "NQZ26",
            "MNQZ26",
            "XYZ100",
            "xyz:XYZ100",
            "USTEC",
            "NAS100",
        ):
            self.assertEqual(family_for(s), "NQ", s)
        self.assertEqual(family_for("MNQ", "ES"), "ES")  # a forced choice wins

    def test_contract_details(self) -> None:
        self.assertEqual(root_symbol("MNQZ26"), "MNQ")
        self.assertEqual(instrument_for("MES").point_value, 5.0)
        self.assertEqual(instrument_for("MNQ").point_value, 2.0)
        self.assertEqual(instrument_for("NQ").tick(), 0.25)
        self.assertEqual(instrument_for("SP500").venue, "HYPERLIQUID")
        # Hyperliquid: 5 significant figures
        self.assertAlmostEqual(instrument_for("SP500").tick(6812.3), 0.1)
        self.assertAlmostEqual(instrument_for("XYZ100").tick(25031.0), 1.0)
        self.assertAlmostEqual(instrument_for("XYZ100").tick(9876.5), 0.1)
        unknown = instrument_for("FOO")
        self.assertFalse(unknown.known)
        self.assertEqual((unknown.family, unknown.tick()), ("ES", 0.25))  # the old default


class CmeCalendarTests(unittest.TestCase):
    def test_globex_hours(self) -> None:
        # 2026-11-13 is a Friday; Chicago is UTC-6 in November.
        cases = {
            _ms(2026, 11, 13, 21, 59): True,  # Fri 3:59 PM CT
            _ms(2026, 11, 13, 22, 0): False,  # Fri 4:00 PM CT: weekend close
            _ms(2026, 11, 14, 18, 0): False,  # Saturday
            _ms(2026, 11, 15, 22, 59): False,  # Sun 4:59 PM CT
            _ms(2026, 11, 15, 23, 0): True,  # Sun 5:00 PM CT: open
            _ms(2026, 11, 16, 22, 30): False,  # Mon 4:30 PM CT: daily break
            _ms(2026, 11, 16, 23, 0): True,  # Mon 5:00 PM CT
            _ms(2026, 7, 13, 21, 30): False,  # Mon 4:30 PM CDT (UTC-5): daily break in summer
            _ms(2026, 7, 13, 20, 30): True,
        }
        got = cme_open(np.array(list(cases), dtype=np.int64))
        self.assertEqual(list(got), list(cases.values()))

    def test_only_24_7_markets_are_filtered(self) -> None:
        t = np.array([_ms(2026, 11, 14, 18, 0), _ms(2026, 11, 16, 15, 0)], dtype=np.int64)
        self.assertIsNone(session_rows("ES", t))
        self.assertEqual(list(session_rows("XYZ100", t)), [1])


def _bars(symbol: str, t: np.ndarray, o, h, lo, c) -> BarTensor:
    data = np.stack([o, h, lo, c], axis=-1)[:, None, :]
    return BarTensor(
        data=data,
        time=t.astype("datetime64[ms]"),
        assets=np.array([symbol], dtype=object),
        fields=np.array(["open", "high", "low", "close"], dtype=object),
    )


class TablePerMarketTests(unittest.TestCase):
    def test_nq_table_differs_from_es(self) -> None:
        self.assertNotEqual(ZONE_STATS[(1, 8)], ZONE_STATS_NQ[(1, 8)])

    def test_am_tbr_uses_the_chart_symbols_table(self) -> None:
        # 25 weekdays of flat 1-minute AM sessions with a small daily move, then a touch.
        rng = np.random.default_rng(1)
        days = [
            d
            for d in range(1, 40)
            if datetime(2026, 9, d if d <= 30 else d - 30, tzinfo=timezone.utc).weekday() < 5
        ][:26]
        rows = []
        for i, d in enumerate(days):
            month, day = (9, d) if d <= 30 else (10, d - 30)
            start = _ms(2026, month, day, 12, 0)  # 8:00 New York (EDT)
            px = 6000.0
            for m in range(240):
                step = rng.normal(0, 1.0)
                o, c = px, px + step
                rows.append((start + m * 60_000, o, max(o, c) + 0.25, min(o, c) - 0.25, c))
                px = c
        arr = np.array(rows)
        t = arr[:, 0].astype(np.int64)
        es = AmTBR().batch(_bars("MES", t, *arr[:, 1:].T), {}).data[:, 0, :]
        nq = AmTBR().batch(_bars("MNQ", t, *arr[:, 1:].T), {}).data[:, 0, :]
        from indicator_engine.indicators.am_tbr import COL

        touched = np.isfinite(es[:, COL["stretch_near"]])
        self.assertTrue(touched.any())
        self.assertFalse(
            np.allclose(es[touched, COL["stretch_far"]], nq[touched, COL["stretch_far"]])
        )
        # same lines (same data), different zone tables
        np.testing.assert_allclose(es[:, COL["+0.25"]], nq[:, COL["+0.25"]], equal_nan=True)

    def test_breaks_tick_follows_the_instrument(self) -> None:
        # Prior RTH high 6000; today trades exactly 0.1 above it.
        t0 = _ms(2026, 11, 16, 14, 30)  # Mon 9:30 New York
        t1 = _ms(2026, 11, 17, 14, 30)  # Tue 9:30
        t = np.r_[t0 + np.arange(390) * 60_000, t1 + np.arange(390) * 60_000].astype(np.int64)
        h = np.r_[np.full(390, 6000.0), np.full(390, 5990.0)]
        h[390 + 100] = 6000.1
        low = h - 20
        o = c = h - 10
        es = breaks(t, o, h, low, c, show="rth", tick=instrument_for("ES").tick())
        self.assertTrue(np.isnan(es[-1, BC["rth_hit_h"]]))  # 0.1 is not a full ES tick past
        sp = Breaks().batch(_bars("SP500", t, o, h, low, c), {"show": "rth"}).data[:, 0, :]
        self.assertTrue(np.isfinite(sp[-1, BC["rth_hit_h"]]))  # SP500 near 6,000 moves in 0.1 steps

    def test_hyperliquid_weekend_bars_are_left_out(self) -> None:
        # A Saturday hour on XYZ100 gets no hour stats; the same bars on NQ would.
        start = _ms(2026, 11, 14, 14, 0)  # Sat 9:00 New York
        t = (start + np.arange(180) * 60_000).astype(np.int64)
        px = 25000 + np.sin(np.arange(180) / 7) * 20
        out_hl = HourStats().batch(_bars("XYZ100", t, px, px + 3, px - 3, px), {}).data[:, 0, :]
        out_nq = HourStats().batch(_bars("NQ", t, px, px + 3, px - 3, px), {}).data[:, 0, :]
        self.assertTrue(np.isnan(out_hl).all())
        self.assertTrue(np.isfinite(out_nq).any())


if __name__ == "__main__":
    unittest.main()
