import numpy as np
import pandas as pd
from indicator_engine.indicators.seiz import COL, OUTPUTS, SEIZ, TABLES, market_for, seiz


def _bars(start: str, minutes: int, path):
    t = pd.date_range(start, periods=minutes, freq="1min", tz="America/New_York")
    ms = (t.tz_convert("UTC").as_unit("ns").asi8 // 1_000_000).astype(np.int64)
    c = np.asarray(path, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return ms, o, np.maximum(o, c) + 0.25, np.minimum(o, c) - 0.25


def test_market_for_names():
    assert market_for("NQ 12-26") == "NQ"
    assert market_for("xyz:XYZ100") == "NQ"
    assert market_for("MES 12-26") == "ES"
    assert market_for("anything", "nq") == "NQ"


def test_hour_lines_and_auto_switch():
    # 9:00-9:59 ranges 100-110; 10:00 opens at 105 then rallies through 110.
    first = np.linspace(100, 110, 30).tolist() + np.linspace(110, 105, 30).tolist()
    second = [105.0] * 20 + np.linspace(105, 130, 40).tolist()
    ms, o, h, lo = _bars("2026-11-10 09:00", 120, first + second)
    out = seiz(ms, o, h, lo, market="NQ", show=["h1"], tick=0.25)
    i = 70  # 10:10, still inside the prior hour
    opn = out[i, COL["h1_open"]]
    assert opn == o[60]
    il75 = round(round(opn * (1 - TABLES["NQ"]["h1"]["il"][1] / 100) / 0.25) * 0.25, 6)
    assert out[i, COL["h1_il75"]] == il75
    assert np.isfinite(out[i, COL["h1_ih75"]])
    assert np.isnan(out[i, COL["h1_eh85"]])          # external high hidden until the break
    assert np.isnan(out[i, COL["h1_ih50"]])          # simple detail: no 50% band
    j = 115  # 10:55, after breaking the 9:00 hour high
    assert np.isnan(out[j, COL["h1_ih75"]])
    assert out[j, COL["h1_eh85"]] == round(round((out[j, COL["h1_ph"]] + opn * TABLES["NQ"]["h1"]["eh"][2] / 100) / 0.25) * 0.25, 6)
    assert np.isfinite(out[j, COL["h1_il75"]])       # low side still internal


def test_full_detail_and_batch_shape():
    ms, o, h, lo = _bars("2026-11-10 08:00", 240, 100 + np.sin(np.arange(240) / 9) * 3)
    full = seiz(ms, o, h, lo, market="ES", show=["h1"], detail="full")
    assert np.isfinite(full[200, COL["h1_il50"]]) or np.isfinite(full[200, COL["h1_el50"]])
    from indicator_engine.core.bars import BarTensor
    data = np.stack([o, h, lo, o], axis=1)[:, None, :]
    bt = BarTensor(data=data, time=pd.to_datetime(ms, unit="ms", utc=True).values,
                   assets=np.array(["ES 12-26"], dtype=object),
                   fields=np.array(["open", "high", "low", "close"], dtype=object))
    res = SEIZ().batch(bt, {"show": "h1, h4"})
    assert res.data.shape == (240, 1, len(OUTPUTS))
