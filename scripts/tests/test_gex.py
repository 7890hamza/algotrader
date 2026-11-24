"""GEX math checks on a made-up option chain (no internet needed)."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("gex", Path(__file__).resolve().parents[1] / "gex.py")
gex = importlib.util.module_from_spec(spec)
sys.modules["gex"] = gex
spec.loader.exec_module(gex)
Opt = gex.Opt


def test_gamma_peaks_at_the_money():
    atm = gex.gamma(100, 100, 0.2, 0.1)
    assert atm > gex.gamma(100, 110, 0.2, 0.1) > 0
    assert gex.gamma(100, 100, 0.2, 0.01) > atm  # closer to expiry: more gamma at the money


def test_walls_and_flip():
    t = 20 / 365
    opts = [
        Opt(5100, 50_000, 0.15, t, True),   # big call strike above
        Opt(4900, 60_000, 0.18, t, False),  # big put strike below
        Opt(5000, 5_000, 0.16, t, True),
        Opt(5000, 5_000, 0.16, t, False),
    ]
    lv = gex.levels(opts, 5000)
    assert lv["callWall"]["strike"] == 5100
    assert lv["putWall"]["strike"] == 4900
    f = lv["flip"]
    assert f is not None and 4900 < f < 5100  # gamma turns negative between the two walls
    assert sum(gex.gex_at(opts, 5090).values()) > 0  # near the call wall: positive
    assert sum(gex.gex_at(opts, 4910).values()) < 0  # near the put wall: negative
