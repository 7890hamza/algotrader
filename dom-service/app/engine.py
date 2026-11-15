"""The memory DOM's engine: the live book, and what happened to every big resting order.

Feed (from NinjaTrader, see ninjatrader/AlgoTraderDomBridge.cs): resting size by price
("d"), best bid / ask ("q") and trades ("x", buy = lifted the ask, sell = hit the bid).

A *big* order is a price whose resting size reaches ``max(min_size, factor x median size of
that side)``. Each one is followed until it leaves the book:

* size leaving a price is matched against the trades at that price (within ~2 s before to
  0.3 s after the change): matched size was **filled**, the rest was **pulled** (cancelled);
* **held**: price traded into it and then moved ``hold_ticks`` away while at least half of
  its size was still there (it can hold several times);
* when it leaves (under a quarter of its peak), it ends as **filled** (most of it traded)
  or **pulled** (most of it cancelled). A level that only scrolled out of the visible
  depth is dropped without an event.

After every event the engine watches price for 5 minutes and stores how far it went away
from the level (bounce) and through it, and where it was after 1 and 5 minutes. Positive
numbers mean "away from the level" (up for a bid, down for an offer).
"""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
MATCH_BEFORE_MS = 2_000
MATCH_AFTER_MS = 300
REACTION_MS = 300_000


def trading_day(t_ms: int) -> str:
    """CME trading day: a new one starts at 3 PM Pacific."""
    local = datetime.fromtimestamp(t_ms / 1000, PT)
    if local.hour >= 15:
        local += timedelta(days=1)
    return local.date().isoformat()


@dataclass
class Episode:
    side: str  # "b" bid / "a" offer
    tick: int
    start: int
    size: int
    peak: int
    filled: int = 0
    pulled: int = 0
    absorbed: int = 0  # traded into it while it rested
    touched: bool = False
    tests: int = 0
    holds: int = 0


@dataclass
class Event:
    id: int
    day: str
    sym: str
    kind: str  # pulled / filled / held
    side: str
    price: float
    t: int
    peak: int
    size: int
    filled: int
    pulled: int
    absorbed: int
    tests: int
    dist_ticks: int  # how far price was from it when it happened
    ref: float  # last trade then
    away: float = 0.0  # best move away from the level within 5 min (points)
    through: float = 0.0  # worst move through it
    m1: float | None = None  # net move after 1 min (away = positive)
    m5: float | None = None
    done: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Config:
    min_size: int = 100
    factor: float = 2.5
    hold_ticks: int = 8
    close_frac: float = 0.25


@dataclass
class Engine:
    cfg: Config = field(default_factory=Config)
    on_event: Callable[[Event, bool], None] | None = None  # (event, final)
    sym: str = ""
    tick: float = 0.25
    book: dict[str, dict[int, int]] = field(default_factory=lambda: {"b": {}, "a": {}})
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    last_t: int = 0
    day: str = ""
    vol: dict[int, list[int]] = field(
        default_factory=lambda: defaultdict(lambda: [0, 0])
    )  # [sold, bought]
    episodes: dict[tuple[str, int], Episode] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    _trades: dict[tuple[str, int], deque] = field(default_factory=lambda: defaultdict(deque))
    _decreases: deque = field(default_factory=deque)
    _watch: list[Event] = field(default_factory=list)
    _next_id: int = 1

    # ---- feed ---------------------------------------------------------------------------
    def handle(self, msg: dict[str, Any]) -> None:
        k = msg.get("k")
        if k == "hello":
            self.sym = str(msg.get("sym", ""))
            self.tick = float(msg.get("tick") or 0.25)
        elif k == "reset":
            self.book = {"b": {}, "a": {}}
            self.episodes.clear()
            self._decreases.clear()
        elif k == "d":
            self._depth(int(msg["t"]), str(msg["s"]), float(msg["p"]), int(msg["v"]))
        elif k == "q":
            self.bid, self.ask = float(msg["b"]), float(msg["a"])
        elif k == "x":
            self._trade(int(msg["t"]), float(msg["p"]), int(msg["v"]), str(msg.get("s", "")))
        t = int(msg.get("t") or 0)
        if t:
            self._settle(t)

    def tk(self, price: float) -> int:
        return round(price / self.tick)

    def px(self, tick: int) -> float:
        return round(tick * self.tick, 6)

    # ---- trades -------------------------------------------------------------------------
    def _trade(self, t: int, price: float, v: int, side: str) -> None:
        day = trading_day(t)
        if day != self.day:
            self.day = day
            self.vol.clear()
        tick = self.tk(price)
        if side == "sell":
            self.vol[tick][0] += v
        elif side == "buy":
            self.vol[tick][1] += v
        self.last, self.last_t = price, t
        # a sell hits resting bids at that price, a buy lifts resting offers
        hit = "b" if side == "sell" else "a" if side == "buy" else None
        if hit:
            self._trades[(hit, tick)].append([t, v])
            ep = self.episodes.get((hit, tick))
            if ep:
                ep.absorbed += v
                if not ep.touched:
                    ep.touched = True
                    ep.tests += 1
        self._check_holds(price, t)
        self._react(price, t)

    def _check_holds(self, price: float, t: int) -> None:
        tick = self.tk(price)
        for ep in self.episodes.values():
            if not ep.touched:
                continue
            away = (tick - ep.tick) if ep.side == "b" else (ep.tick - tick)
            if away >= self.cfg.hold_ticks and ep.size >= ep.peak / 2:
                ep.touched = False
                ep.holds += 1
                self._emit("held", ep, t)

    # ---- depth --------------------------------------------------------------------------
    def _depth(self, t: int, side: str, price: float, v: int) -> None:
        tick = self.tk(price)
        levels = self.book[side]
        old = levels.get(tick, 0)
        if v > 0:
            levels[tick] = v
        else:
            levels.pop(tick, None)
        if v < old:
            out_of_view = v == 0 and self._beyond_view(side, tick)
            self._decreases.append((t, side, tick, old - v, out_of_view, self.last))
        ep = self.episodes.get((side, tick))
        if ep:
            ep.size = v
            ep.peak = max(ep.peak, v)
        elif v >= self._big(side):
            self.episodes[(side, tick)] = Episode(side, tick, t, v, v)

    def _beyond_view(self, side: str, tick: int) -> bool:
        """Removed from past the deepest visible price: it scrolled out, it wasn't pulled."""
        rest = self.book[side]
        if not rest:
            return False
        return tick < min(rest) if side == "b" else tick > max(rest)

    def _big(self, side: str) -> float:
        sizes = list(self.book[side].values())
        med = statistics.median(sizes) if len(sizes) >= 3 else 0
        return max(self.cfg.min_size, self.cfg.factor * med)

    def _settle(self, now: int) -> None:
        """Classify size that left the book once the trades around it have arrived."""
        while self._decreases and self._decreases[0][0] <= now - MATCH_AFTER_MS:
            t, side, tick, gone, out_of_view, ref = self._decreases.popleft()
            q = self._trades[(side, tick)]
            while q and q[0][0] < t - MATCH_BEFORE_MS:
                q.popleft()
            filled = 0
            for tr in q:
                if tr[0] > t + MATCH_AFTER_MS or filled >= gone:
                    break
                take = min(tr[1], gone - filled)
                tr[1] -= take
                filled += take
            while q and q[0][1] <= 0:
                q.popleft()
            ep = self.episodes.get((side, tick))
            if not ep:
                continue
            ep.filled += filled
            ep.pulled += gone - filled
            if ep.size < ep.peak * self.cfg.close_frac:
                del self.episodes[(side, tick)]
                if out_of_view and ep.size == 0 and filled == 0:
                    continue
                self._emit("filled" if ep.filled >= ep.pulled else "pulled", ep, t, ref)
        self._react_time(now)

    # ---- events and reactions -----------------------------------------------------------
    def _emit(self, kind: str, ep: Episode, t: int, ref: float | None = None) -> None:
        if ref is None:
            ref = self.last if self.last is not None else self.px(ep.tick)
        dist = abs(self.tk(ref) - ep.tick)
        ev = Event(
            self._next_id,
            trading_day(t),
            self.sym,
            kind,
            ep.side,
            self.px(ep.tick),
            t,
            ep.peak,
            ep.size,
            ep.filled,
            ep.pulled,
            ep.absorbed,
            ep.tests,
            dist,
            ref,
        )
        self._next_id += 1
        self.events.append(ev)
        self._watch.append(ev)
        if self.on_event:
            self.on_event(ev, False)

    def _react(self, price: float, t: int) -> None:
        for ev in self._watch:
            if t - ev.t > REACTION_MS:
                continue
            sgn = 1 if ev.side == "b" else -1
            move = round((price - ev.ref) * sgn, 4)
            ev.away = max(ev.away, move)
            ev.through = max(ev.through, -move)
            if ev.m1 is None and t - ev.t >= 60_000:
                ev.m1 = move
        self._react_time(t)

    def _react_time(self, now: int) -> None:
        keep = []
        for ev in self._watch:
            if now - ev.t >= REACTION_MS:
                sgn = 1 if ev.side == "b" else -1
                last = self.last if self.last is not None else ev.ref
                ev.m5 = round((last - ev.ref) * sgn, 4)
                if ev.m1 is None:
                    ev.m1 = ev.m5
                ev.done = True
                if self.on_event:
                    self.on_event(ev, True)
            else:
                keep.append(ev)
        self._watch = keep

    # ---- what the panel shows -----------------------------------------------------------
    def snapshot(self, rows: int = 60) -> dict[str, Any]:
        center = self.tk(self.last) if self.last is not None else None
        near = (lambda tk: True) if center is None else (lambda tk: abs(tk - center) <= rows)
        return {
            "sym": self.sym,
            "tick": self.tick,
            "last": self.last,
            "lastT": self.last_t,
            "bid": self.bid,
            "ask": self.ask,
            "bids": [[self.px(k), v] for k, v in sorted(self.book["b"].items(), reverse=True)],
            "asks": [[self.px(k), v] for k, v in sorted(self.book["a"].items())],
            "vol": [[self.px(k), s, b] for k, (s, b) in self.vol.items() if near(k)],
            "big": [
                [ep.side, self.px(ep.tick), ep.size, ep.peak, ep.holds, ep.absorbed]
                for ep in self.episodes.values()
            ],
        }
