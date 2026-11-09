from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_hours import cme_closed, drop_closed_bars

CT = ZoneInfo("America/Chicago")


def ms(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=CT).timestamp() * 1000)


def test_weekend_and_daily_break_are_closed():
    # Fri Nov 6 2026 .. Sun Nov 8 2026
    assert not cme_closed(ms(2026, 11, 6, 15, 59))
    assert cme_closed(ms(2026, 11, 6, 16, 0))
    assert cme_closed(ms(2026, 11, 7, 12, 0))
    assert cme_closed(ms(2026, 11, 8, 16, 59))
    assert not cme_closed(ms(2026, 11, 8, 17, 0))
    assert cme_closed(ms(2026, 11, 10, 16, 30))  # Tuesday break
    assert not cme_closed(ms(2026, 11, 10, 17, 0))


def test_drop_closed_bars_only_for_cme_symbols():
    bars = [{"timestamp_ms": ms(2026, 11, 7, 13, 1)}, {"timestamp_ms": ms(2026, 11, 8, 17, 0)}]
    assert drop_closed_bars("ES", bars) == bars[1:]
    assert drop_closed_bars("BTCUSD", bars) == bars
