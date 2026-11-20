import numpy as np
import pandas as pd
from indicator_engine.core.bars import BarTensor
from indicator_engine.indicators.setups import COL, OUTPUTS, SETUPS, Setups, setups


def _walk(days: int, seed: int = 3):
    t = pd.date_range("2026-03-01", periods=days * 1440, freq="1min", tz="UTC")
    et = t.tz_convert("America/New_York")
    sat, sun = et.dayofweek == 5, (et.dayofweek == 6) & (et.hour < 18)
    weekend = sat | sun | ((et.dayofweek == 4) & (et.hour > 17))
    keep = ~((et.hour == 17) | weekend)
    t = t[keep]
    c = 6000 + np.cumsum(np.random.default_rng(seed).normal(0, 1.2, len(t)))
    o = np.r_[c[0], c[:-1]]
    ms = (t.as_unit("ns").asi8 // 1_000_000).astype(np.int64)
    return ms, o, np.maximum(o, c) + 0.5, np.minimum(o, c) - 0.5, c


def test_every_trade_is_complete_and_follows_the_rules():
    ms, o, h, lo, c = _walk(75)
    out = setups(ms, o, h, lo, c, asset="ES", target=10, stop=3, hold=60, cost=0.5)
    n = 0
    for s in SETUPS:
        rows = np.where(np.isfinite(out[:, COL[f"{s}_dir"]]))[0]
        n += len(rows)
        for r in rows:
            how, pts, d = out[r, COL[f"{s}_how"]], out[r, COL[f"{s}_pts"]], out[r, COL[f"{s}_dir"]]
            assert d == (1 if s in "ABC" else -1)
            assert out[r, COL[f"{s}_entry"]] == o[r]                     # enters at that bar's open
            assert ms[r] <= out[r, COL[f"{s}_exit_ms"]] < ms[r] + 60 * 60_000
            if how == 1:
                assert pts == 9.5
            elif how == -1:
                assert pts == -3.5
            else:
                assert -3.5 < pts < 9.5
        gaps = np.diff(ms[rows])
        assert (gaps >= 12 * 300_000).all()  # one trade at a time per setup
    assert n > 0


def test_batch_shape():
    ms, o, h, lo, c = _walk(45)
    data = np.stack([o, h, lo, c], axis=1)[:, None, :]
    fields = np.array(["open", "high", "low", "close"], dtype=object)
    bt = BarTensor(data=data, time=pd.to_datetime(ms, unit="ms", utc=True).values,
                   assets=np.array(["ES"], dtype=object), fields=fields)
    res = Setups().batch(bt, {})
    assert res.data.shape == (len(ms), 1, len(OUTPUTS))
