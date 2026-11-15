from app.engine import Config, Engine, trading_day
from app.store import Store

T0 = 1_794_248_580_000  # Mon Nov 9 2026 10:23 PT


def book(e: Engine, t: int = T0) -> None:
    """A normal book around 100.00: 20 lots a level, one 400-lot bid at 99.00."""
    e.handle({"k": "hello", "sym": "ES 12-26", "tick": 0.25})
    for i in range(10):
        e.handle({"k": "d", "t": t, "s": "b", "p": 99.75 - i * 0.25, "v": 400 if i == 3 else 20})
        e.handle({"k": "d", "t": t, "s": "a", "p": 100.0 + i * 0.25, "v": 20})
    e.handle({"k": "x", "t": t, "p": 100.0, "v": 1, "s": "buy"})


def make() -> tuple[Engine, list]:
    got: list = []
    e = Engine(Config(min_size=100), on_event=lambda ev, final: got.append((ev.kind, final, ev)))
    book(e)
    return e, got


def test_big_bid_is_followed():
    e, _ = make()
    assert ("b", round(99.0 / 0.25)) in e.episodes
    assert len(e.episodes) == 1


def test_pulled_without_trades():
    e, got = make()
    e.handle({"k": "d", "t": T0 + 1000, "s": "b", "p": 99.0, "v": 0})
    e.handle({"k": "x", "t": T0 + 2000, "p": 100.0, "v": 1, "s": "buy"})
    kinds = [(k, f) for k, f, _ in got]
    assert kinds == [("pulled", False)]
    ev = got[0][2]
    assert ev.pulled == 400 and ev.filled == 0 and ev.side == "b" and ev.price == 99.0
    assert ev.dist_ticks == 4


def test_filled_when_trades_match():
    e, got = make()
    # price comes down and sells 390 into the bid, which empties
    e.handle({"k": "x", "t": T0 + 1000, "p": 99.0, "v": 390, "s": "sell"})
    e.handle({"k": "d", "t": T0 + 1050, "s": "b", "p": 99.0, "v": 10})
    e.handle({"k": "x", "t": T0 + 2000, "p": 98.75, "v": 1, "s": "sell"})
    assert [k for k, _, _ in got] == ["filled"]
    assert got[0][2].filled == 390 and got[0][2].absorbed == 390


def test_trade_arriving_just_after_the_size_change_still_counts():
    e, got = make()
    e.handle({"k": "d", "t": T0 + 1000, "s": "b", "p": 99.0, "v": 0})
    e.handle({"k": "x", "t": T0 + 1100, "p": 99.0, "v": 400, "s": "sell"})
    e.handle({"k": "x", "t": T0 + 2000, "p": 98.75, "v": 1, "s": "sell"})
    assert [k for k, _, _ in got] == ["filled"]


def test_held_then_reaction():
    e, got = make()
    e.handle({"k": "x", "t": T0 + 1000, "p": 99.0, "v": 60, "s": "sell"})
    e.handle({"k": "d", "t": T0 + 1000, "s": "b", "p": 99.0, "v": 340})
    e.handle({"k": "x", "t": T0 + 5000, "p": 101.0, "v": 1, "s": "buy"})  # 8 ticks away
    held = [ev for k, _, ev in got if k == "held"]
    assert len(held) == 1 and held[0].absorbed == 60 and held[0].tests == 1
    assert ("b", 396) in e.episodes  # still there
    e.handle({"k": "x", "t": T0 + 70_000, "p": 102.0, "v": 1, "s": "buy"})
    e.handle({"k": "x", "t": T0 + 400_000, "p": 100.5, "v": 1, "s": "sell"})
    final = [ev for k, f, ev in got if k == "held" and f]
    assert final and final[0].done
    ev = final[0]
    assert ev.away == 1.0 and ev.m1 == 1.0 and ev.m5 == -0.5


def test_level_scrolling_out_of_view_is_not_a_pull():
    e, got = make()
    e.handle({"k": "d", "t": T0, "s": "b", "p": 97.5, "v": 300})  # new deepest big bid
    assert ("b", 390) in e.episodes
    e.handle({"k": "d", "t": T0 + 1000, "s": "b", "p": 97.5, "v": 0})  # price moved up: falls off
    e.handle({"k": "x", "t": T0 + 2000, "p": 100.0, "v": 1, "s": "buy"})
    assert not [k for k, _, _ in got]
    assert ("b", 390) not in e.episodes


def test_volume_columns_and_day_roll():
    e, _ = make()
    e.handle({"k": "x", "t": T0 + 10, "p": 99.75, "v": 5, "s": "sell"})
    snap = e.snapshot()
    assert [99.75, 5, 0] in snap["vol"]
    assert snap["bids"][0] == [99.75, 20]
    assert trading_day(T0) == "2026-11-09"
    assert trading_day(T0 + 5 * 3_600_000) == "2026-11-10"  # after 3 PM PT


def test_store_round_trip(tmp_path):
    st = Store(tmp_path / "m.sqlite")
    e = Engine(Config(min_size=100), on_event=st.save)
    book(e)
    e.handle({"k": "d", "t": T0 + 1000, "s": "b", "p": 99.0, "v": 0})
    e.handle({"k": "x", "t": T0 + 2000, "p": 99.75, "v": 1, "s": "sell"})
    e.handle({"k": "x", "t": T0 + 400_000, "p": 98.0, "v": 1, "s": "sell"})
    rows = st.day_events("2026-11-09")
    assert len(rows) == 1 and rows[0]["kind"] == "pulled" and rows[0]["done"] == 1
    assert rows[0]["m5"] == -2.0
    s = st.stats("ES")
    assert s[0]["kind"] == "pulled" and s[0]["n"] == 1 and s[0]["awayPct"] == 0.0
