import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))

from labkit import data  # noqa: E402
from harness import run_cycle, make_logger  # noqa: E402


def bar(ms, p):
    return {"timestamp_ms": ms, "open": p, "high": p + 1, "low": p - 1, "close": p}


class DataTests(unittest.TestCase):
    def test_feed_appends_without_duplicates_and_splices_after_history(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            t0 = 1_793_000_000_000
            np.savez(d / "ES_2026.npz", t=np.array([t0, t0 + 60_000], np.int64), o=np.ones(2, np.float32), h=np.ones(2, np.float32), l=np.ones(2, np.float32), c=np.ones(2, np.float32))
            self.assertEqual(data.append_feed(d, [bar(t0 + 60_000, 5), bar(t0 + 120_000, 6)]), 2)
            self.assertEqual(data.append_feed(d, [bar(t0 + 120_000, 6), bar(t0 + 180_000, 7)]), 1)  # one repeat
            out = data.load(d)
            self.assertEqual(out["t"].tolist(), [t0, t0 + 60_000, t0 + 120_000, t0 + 180_000])
            self.assertEqual(out["c"][1], 1)  # history wins where both have the bar
            self.assertEqual(data.last_bar_ms(d), t0 + 180_000)
            self.assertIn("FEED_2026", data.coverage(d))


class HarnessTests(unittest.TestCase):
    def test_cycle_runs_agents_isolates_failures_and_respects_pause(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            lab = Path(d)
            for name, body in (("good", "def run(ctx):\n    return 'did a thing'\n"), ("bad", "def run(ctx):\n    raise ValueError('boom')\n"), ("sleepy", "def run(ctx):\n    return 'x'\n")):
                (lab / "agents" / name).mkdir(parents=True)
                (lab / "agents" / name / "step.py").write_text(body)
            (lab / "agents" / "sleepy" / "PAUSE").touch()
            status = run_cycle(lab, {"agents": ["good", "bad", "sleepy"]}, make_logger(lab))
            self.assertEqual(status["good"]["summary"], "did a thing")
            self.assertFalse(status["bad"]["ok"])
            self.assertIn("boom", (lab / "agents" / "bad" / "memory" / "errors.log").read_text())
            self.assertEqual(status["sleepy"]["summary"], "paused")
            self.assertTrue(json.loads((lab / "arena" / "status.json").read_text())["harness"])


class TraderClockTests(unittest.TestCase):
    def test_market_hours(self) -> None:
        sys.path.insert(0, str(LAB / "agents" / "trader"))
        from step import market_open
        pt = lambda *a: datetime(*a)
        self.assertTrue(market_open(pt(2026, 11, 6, 10, 0)))   # Friday morning
        self.assertFalse(market_open(pt(2026, 11, 6, 14, 30)))  # Friday after the close
        self.assertFalse(market_open(pt(2026, 11, 7, 12, 0)))  # Saturday
        self.assertTrue(market_open(pt(2026, 11, 8, 15, 5)))   # Sunday evening open
        self.assertFalse(market_open(pt(2026, 11, 9, 14, 20)))  # daily break


if __name__ == "__main__":
    unittest.main()
