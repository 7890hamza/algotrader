import numpy as np
import pandas as pd
from indicator_engine.core.bars import BarTensor
from indicator_engine.indicators.seiz import COL, OUTPUTS, SEIZ, TABLES, market_for, parse_tf, seiz
from indicator_engine.indicators.seiz_frames import TIMEFRAMES, frame_keys


def _bars(start: str, minutes: int, path):
    t = pd.date_range(start, periods=minutes, freq="1min", tz="America/New_York")
    ms = (t.tz_convert("UTC").as_unit("ns").asi8 // 1_000_000).astype(np.int64)
    c = np.asarray(path, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return ms, o, np.maximum(o, c) + 0.25, np.minimum(o, c) - 0.25


def _local(ts: str) -> np.ndarray:
    t = pd.Timestamp(ts)
    return np.array([int(t.value // 1_000_000)])


def test_names_and_timeframes():
    assert market_for("NQ 12-26") == "NQ" and market_for("xyz:XYZ100") == "NQ"
    assert market_for("MES 12-26") == "ES"
    assert parse_tf("daily") == "1d" and parse_tf("4H") == "4h"
    assert len(TIMEFRAMES) == 16 and set(TABLES["NQ"]) == set(TIMEFRAMES)


def test_frames_follow_the_cme_clock():
    # 4h candles count from the 6 PM open (10 AM-2 PM is one); 5h's last candle stops at 5 PM.
    _, s, e = frame_keys(_local("2026-11-12 11:30"), "4h")
    assert pd.Timestamp(int(s[0]), unit="ms").strftime("%H:%M") == "10:00"
    assert pd.Timestamp(int(e[0]), unit="ms").strftime("%H:%M") == "14:00"
    _, s, e = frame_keys(_local("2026-11-12 16:30"), "5h")    # 6 PM, 11 PM, 4 AM, 9 AM, 2 PM
    assert pd.Timestamp(int(s[0]), unit="ms").strftime("%H:%M") == "14:00"
    assert pd.Timestamp(int(e[0]), unit="ms").strftime("%H:%M") == "17:00"
    _, s, e = frame_keys(_local("2026-11-12 20:00"), "1d")   # evening belongs to the next day
    assert pd.Timestamp(int(s[0]), unit="ms").strftime("%m-%d %H:%M") == "11-12 18:00"
    _, s, e = frame_keys(_local("2026-11-11 09:00"), "1w")   # Wednesday
    assert pd.Timestamp(int(s[0]), unit="ms").strftime("%a %H:%M") == "Sun 18:00"
    assert pd.Timestamp(int(e[0]), unit="ms").strftime("%a %H:%M") == "Fri 17:00"


def test_bands_switch_from_internal_to_external():
    first = np.linspace(100, 110, 30).tolist() + np.linspace(110, 105, 30).tolist()
    second = [105.0] * 20 + np.linspace(105, 130, 40).tolist()
    ms, o, h, lo = _bars("2026-11-10 09:00", 120, first + second)
    out = seiz(ms, o, h, lo, market="NQ", zone_tf="1h", stat_zone=True, dashboard=True)
    i = 70  # 10:10, still inside the 9:00 range
    opn = out[i, COL["open"]]
    assert opn == o[60]
    il75 = round(round(opn * (1 - TABLES["NQ"]["1h"]["il"][1] / 100) / 0.25) * 0.25, 6)
    assert out[i, COL["il75"]] == il75
    assert np.isfinite(out[i, COL["ih50"]]) and np.isnan(out[i, COL["eh50"]])
    assert out[i, COL["st_h_lo"]] <= out[i, COL["st_h_mid"]] <= out[i, COL["st_h_hi"]]
    j = 115  # 10:55, after breaking the 9:00 high
    assert np.isnan(out[j, COL["ih50"]]) and np.isfinite(out[j, COL["eh99"]])
    assert out[j, COL["eh50"]] >= out[j, COL["ph"]]
    assert np.isfinite(out[j, COL["il50"]])          # low side still internal
    assert out[j, COL["d_1h_hi"]] >= 100              # dashboard: external high
    assert 0 < out[j, COL["d_1h_pg"]] <= 100
    assert out[j, COL["end"]] - out[j, COL["start"]] == 3_600_000
    # candle strip: the 1h candle measured in the 9:00 candle's range; its high broke above (> 1)
    assert out[j, COL["d_1h_h"]] > 1 and 0 <= out[j, COL["d_1h_o"]] <= 1
    assert out[j, COL["d_1h_l"]] <= out[j, COL["d_1h_o"]] <= out[j, COL["d_1h_h"]]


def test_batch_shape_and_options():
    ms, o, h, lo = _bars("2026-11-10 08:00", 240, 100 + np.sin(np.arange(240) / 9) * 3)
    data = np.stack([o, h, lo, o], axis=1)[:, None, :]
    bt = BarTensor(data=data, time=pd.to_datetime(ms, unit="ms", utc=True).values,
                   assets=np.array(["ES 12-26"], dtype=object),
                   fields=np.array(["open", "high", "low", "close"], dtype=object))
    res = SEIZ().batch(bt, {"zone_tf": "30m", "dashboard": "off"})
    assert res.data.shape == (240, 1, len(OUTPUTS))
    assert np.isnan(res.data[:, 0, COL["d_1h_hi"]]).all()
    assert SEIZ.spec.parameters["zone_tf"]["options"] == TIMEFRAMES
