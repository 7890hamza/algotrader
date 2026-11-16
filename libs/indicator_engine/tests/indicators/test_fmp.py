import numpy as np
import pandas as pd
from indicator_engine.core.bars import BarTensor
from indicator_engine.indicators.fmp import COL, FMP, OUTPUTS, SIGMA, fmp


def _bars(start: str, minutes: int, seed: int = 0):
    t = pd.date_range(start, periods=minutes, freq="1min", tz="America/New_York")
    t = t[(t.hour != 17)]
    ms = (t.tz_convert("UTC").as_unit("ns").asi8 // 1_000_000).astype(np.int64)
    c = 20000 + np.cumsum(np.random.default_rng(seed).normal(0, 3, len(ms)))
    o = np.r_[c[0], c[:-1]]
    return ms, o, np.maximum(o, c) + 1, np.minimum(o, c) - 1


def test_fixed_uses_table_and_hour_open():
    ms, o, h, lo = _bars("2026-11-10 09:00", 180)
    out = fmp(ms, o, h, lo, market="NQ", scale="fixed")
    i = 75  # 10:15
    assert out[i, COL["open"]] == o[60]
    assert out[i, COL["start"]] == ms[60]
    assert out[i, COL["sig30"]] == round(SIGMA["NQ"][10][30], 2)
    assert out[i, COL["sig5"]] < out[i, COL["sig30"]]


def test_adaptive_scales_with_recent_hours():
    ms, o, h, lo = _bars("2026-10-01 00:00", 60 * 24 * 30)
    calm = fmp(ms, o, h, lo, market="NQ", scale="adaptive")
    wild = fmp(ms, o, o + (h - o) * 3, o - (o - lo) * 3, market="NQ", scale="adaptive")
    i = len(ms) - 30
    assert np.isfinite(calm[i, COL["ratio"]])
    assert wild[i, COL["sig15"]] > calm[i, COL["sig15"]] * 1.1


def test_batch_shape():
    ms, o, h, lo = _bars("2026-11-10 08:00", 240)
    data = np.stack([o, h, lo, o], axis=1)[:, None, :]
    bt = BarTensor(data=data, time=pd.to_datetime(ms, unit="ms", utc=True).values,
                   assets=np.array(["ES 12-26"], dtype=object),
                   fields=np.array(["open", "high", "low", "close"], dtype=object))
    res = FMP().batch(bt, {"scale": "fixed"})
    assert res.data.shape == (len(ms), 1, len(OUTPUTS))
    assert res.data[30, 0, COL["sig30"]] == round(SIGMA["ES"][8][30], 2)
