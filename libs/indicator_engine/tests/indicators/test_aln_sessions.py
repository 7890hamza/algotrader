import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from indicator_engine import get_registry
from indicator_engine.indicators.aln_sessions import COL, OUTPUTS, AlnSessions, aln_sessions

NY = ZoneInfo("America/New_York")


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def night(day: datetime, asia: tuple, london: tuple, ny_path: list):
    """5-minute bars: Asia 20:00-02:00 at `asia` (low, high), London 02:00-08:00 at
    `london`, then New York bars following `ny_path` (high, low) pairs from 08:00."""
    t, o, h, lo, c = [], [], [], [], []
    start = datetime(day.year, day.month, day.day, 20, 0, tzinfo=NY) - timedelta(days=1)
    for k in range(72):  # Asia
        t.append(ms(start + timedelta(minutes=5 * k)))
        o.append(asia[0]); c.append(asia[0]); lo.append(asia[0]); h.append(asia[1] if k == 10 else asia[0])
    lstart = start + timedelta(hours=6)
    for k in range(72):  # London
        t.append(ms(lstart + timedelta(minutes=5 * k)))
        o.append(london[0]); c.append(london[0]); lo.append(london[0]); h.append(london[1] if k == 10 else london[0])
    nstart = start + timedelta(hours=12)
    for k, (hh, ll) in enumerate(ny_path):
        t.append(ms(nstart + timedelta(minutes=5 * k)))
        o.append(ll); c.append(ll); lo.append(ll); h.append(hh)
    return t, o, h, lo, c


class AlnTests(unittest.TestCase):
    def run_days(self, nights):
        cols = [[], [], [], [], []]
        for nt in nights:
            for col, vals in zip(cols, nt):
                col.extend(vals)
        t = np.array(cols[0], dtype=np.int64)
        return t, aln_sessions(t, *(np.array(c, dtype=float) for c in cols[1:]))

    def test_partial_up_pattern_and_breaks(self):
        # Asia 100-110, London 105-115: London took Asia's high only -> P3
        ny_path = [(112, 106)] * 6 + [(116, 108)] + [(114, 104)] * 5
        t, out = self.run_days([night(datetime(2026, 10, 7), (100, 110), (105, 115), ny_path)])
        first_ny = 144
        row = out[first_ny]
        self.assertEqual(row[COL["pattern"]], 3)
        self.assertEqual((row[COL["ref_asia_high"]], row[COL["ref_london_low"]]), (110, 105))
        self.assertTrue(np.isnan(row[COL["up_at"]]))
        self.assertEqual(out[first_ny + 6, COL["up_at"]], t[first_ny + 6])
        self.assertEqual(out[first_ny + 7, COL["dn_at"]], t[first_ny + 7])
        self.assertEqual(out[first_ny + 3, COL["ny_high"]], 112)  # running New York range
        self.assertEqual(out[50, COL["asia_high"]], 110)
        self.assertTrue(np.isnan(out[50, COL["pattern"]]))

    def test_recent_codes(self):
        d1 = night(datetime(2026, 10, 6), (100, 110), (95, 109), [(108, 94)] * 12)  # P4, low taken
        d2 = night(datetime(2026, 10, 7), (100, 110), (101, 109), [(111, 100)] * 12)  # P2
        _, out = self.run_days([d1, d2])
        last = out[-1]
        self.assertEqual(last[COL["pattern"]], 2)
        self.assertEqual(last[COL["recent_1"]], 410)  # P4, reached, other side not first
        self.assertTrue(np.isnan(last[COL["recent_2"]]))

    def test_registered(self):
        self.assertIn("aln_sessions", get_registry().list_specs())
        self.assertEqual(AlnSessions().spec.outputs, OUTPUTS)
        self.assertTrue(AlnSessions().spec.sparse_outputs)


if __name__ == "__main__":
    unittest.main()
