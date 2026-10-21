"""MetaTrader 5 market-data adapter (read-only).

Implements the same broker ports as the cTrader adapter so the rest of AlgoTrader
(ingestion, webserver, indicators) keeps working unchanged:

* historical Candles through ``copy_rates_range``,
* live Candles and Ticks by polling the running MT5 terminal,
* symbols through ``symbols_get`` / ``symbol_info``.

The MetaTrader5 Python package only runs on Windows and talks to an MT5 terminal
that is open and logged in on the same machine, so this adapter runs natively on
Windows (see ``broker-service/MT5.md``), not inside Docker.

Trading is deliberately not implemented: order, position and close commands raise
``TradingDisabledError`` and order/position/deal queries return empty lists.

All MetaTrader5 calls happen on one dedicated worker thread because the package
keeps global, non-thread-safe state.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from app.application.interfaces import BrokerPort, MarketDataPort
from app.domain.models import Account, Deal, Order, Position, Symbol, Tick, Trendbar
from app.domain.value_objects import (
    AccountId,
    OrderId,
    PositionId,
    SymbolDescriptor,
    SymbolId,
    Timeframe,
)
from app.infrastructure.stream_registry import TickSubscription, TrendbarSubscription
from app.settings import Mt5Settings

logger = logging.getLogger(__name__)

TickHandler = Callable[[Tick], Awaitable[None]]
TrendbarHandler = Callable[[Trendbar], Awaitable[None]]

TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M2: 2,
    Timeframe.M3: 3,
    Timeframe.M4: 4,
    Timeframe.M5: 5,
    Timeframe.M10: 10,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.H12: 720,
    Timeframe.D1: 1440,
    Timeframe.W1: 10080,
    Timeframe.MN1: 43200,
}

# Bars per historical request window; bounds memory for long backfills.
HISTORY_WINDOW_BARS = 20_000
# Ticks fetched per poll per symbol; a busy ES minute is a few thousand ticks.
TICKS_PER_POLL = 50_000
RECONNECT_DELAY_SECONDS = 3.0
ACCOUNT_TRADE_MODE_DEMO = 0


class TradingDisabledError(RuntimeError):
    """Raised for any trading command: this bridge only reads market data."""


def _url_safe(name: str) -> bool:
    return bool(name) and all(ch.isalnum() or ch in "._-" for ch in name)


def _symbol_id(name: str) -> int:
    """Stable positive integer id for a symbol name (MT5 has no numeric ids)."""
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF


@dataclass(slots=True)
class _TickState:
    mt5_name: str
    alias: str
    digits: int
    handlers: dict[str, TickHandler] = field(default_factory=dict)
    last_msc: int | None = None
    seen_at_last_msc: int = 0


@dataclass(slots=True)
class _BarState:
    mt5_name: str
    alias: str
    timeframe: Timeframe
    digits: int
    handlers: dict[str, TrendbarHandler] = field(default_factory=dict)
    current: tuple | None = None  # (time, open, high, low, close, volume) as last emitted


class Mt5Client(BrokerPort, MarketDataPort):
    """Read-only MetaTrader 5 adapter implementing the broker ports."""

    def __init__(self, settings: Mt5Settings, mt5_module: Any | None = None) -> None:
        self._settings = settings
        self._mt5: Any = mt5_module
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5")
        self._offset_seconds = settings.server_utc_offset_minutes * 60
        self._aliases = dict(settings.symbol_aliases)  # alias -> mt5 name
        self._reverse_aliases = {v.upper(): k for k, v in self._aliases.items()}

        self._connected = False
        self._shutting_down = False
        self._continuity = "v1:" + uuid.uuid4().hex
        self._poll_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._tick_states: dict[str, _TickState] = {}  # key: alias
        self._bar_states: dict[tuple[str, str], _BarState] = {}  # key: (alias, timeframe)
        self._symbol_info_cache: dict[str, Symbol] = {}

    # ------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore[import-not-found]  # noqa: N813
            except ImportError as exc:  # pragma: no cover - depends on platform
                raise RuntimeError(
                    "The MetaTrader5 package is not installed. It only runs on Windows: "
                    "pip install MetaTrader5"
                ) from exc
            self._mt5 = mt5
        await self._call(self._initialize)
        self._connected = True
        self._poll_task = asyncio.create_task(self._poll_loop(), name="mt5-poll")

    async def disconnect(self) -> None:
        self._shutting_down = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
            self._poll_task = None
        if self._mt5 is not None:
            try:
                await self._call(self._mt5.shutdown)
            except Exception:
                logger.exception("MT5 shutdown failed")
        self._connected = False
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def reset_authorized_accounts(self) -> None:  # parity with cTrader adapter
        return None

    def _initialize(self) -> None:
        mt5 = self._mt5
        ok = (
            mt5.initialize(path=self._settings.terminal_path)
            if self._settings.terminal_path
            else mt5.initialize()
        )
        if not ok:
            raise RuntimeError(
                f"Could not connect to MetaTrader 5 ({mt5.last_error()}). "
                "Is MT5 open and logged in?"
            )
        account = mt5.account_info()
        if account is None:
            mt5.shutdown()
            raise RuntimeError("MetaTrader 5 is open but not logged in to an account.")
        if self._settings.require_demo and account.trade_mode != ACCOUNT_TRADE_MODE_DEMO:
            mt5.shutdown()
            raise RuntimeError(
                f"MT5 is logged in to a non-demo account on server {account.server}. "
                "Log in to a demo account, or set MT5_REQUIRE_DEMO=false if you really "
                "mean to read prices from this account (this bridge never trades)."
            )
        logger.info(
            "Connected to MetaTrader 5 server=%s demo=%s",
            account.server,
            account.trade_mode == ACCOUNT_TRADE_MODE_DEMO,
        )

    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    # ------------------------------------------------------------- time helpers

    def _to_server_dt(self, ts_ms: int) -> datetime:
        return datetime.fromtimestamp(ts_ms / 1000 + self._offset_seconds, tz=timezone.utc)

    def _bar_ms(self, server_seconds: int) -> int:
        return (int(server_seconds) - self._offset_seconds) * 1000

    def _tick_ms(self, server_msc: int) -> int:
        return int(server_msc) - self._offset_seconds * 1000

    def _volume(self, row: Any) -> int:
        if self._settings.volume_source == "real":
            return int(row["real_volume"])
        return int(row["tick_volume"])

    def _mt5_timeframe(self, timeframe: Timeframe) -> int:
        return getattr(self._mt5, f"TIMEFRAME_{timeframe.value}")

    # ------------------------------------------------------------- symbols

    def _resolve(self, symbol: str) -> tuple[str, str]:
        """Return (alias, mt5_name) for an AlgoTrader symbol."""
        alias = symbol.upper()
        if alias in self._aliases:
            return alias, self._aliases[alias]
        return alias, alias

    def _symbol_sync(self, symbol: str) -> Symbol | None:
        alias, mt5_name = self._resolve(symbol)
        cached = self._symbol_info_cache.get(alias)
        if cached is not None:
            return cached
        mt5 = self._mt5
        info = mt5.symbol_info(mt5_name)
        if info is None:
            return None
        if not info.visible:
            mt5.symbol_select(mt5_name, True)
        result = Symbol(
            symbol_id=_symbol_id(alias),
            symbol_name=alias,
            digits=int(info.digits),
            pip_position=int(info.digits),
        )
        self._symbol_info_cache[alias] = result
        return result

    async def list_symbols(self, account_id: AccountId | None = None) -> list[SymbolDescriptor]:
        def run() -> list[SymbolDescriptor]:
            descriptors: dict[str, SymbolDescriptor] = {}
            for alias in self._aliases:
                descriptors[alias] = SymbolDescriptor(
                    symbol_id=SymbolId(_symbol_id(alias)), symbol_name=alias, enabled=True
                )
            for info in self._mt5.symbols_get() or ():
                name = str(info.name).upper()
                if name in self._reverse_aliases or not _url_safe(name):
                    continue
                descriptors.setdefault(
                    name,
                    SymbolDescriptor(
                        symbol_id=SymbolId(_symbol_id(name)), symbol_name=name, enabled=True
                    ),
                )
            return sorted(descriptors.values(), key=lambda d: d.symbol_name)

        return await self._call(run)

    async def get_symbol(self, account_id: AccountId, symbol: str) -> Symbol:
        # The router answers 404 when this returns None.
        return await self._call(self._symbol_sync, symbol)  # type: ignore[return-value]

    async def _require_symbol(self, symbol: str) -> Symbol:
        info = await self._call(self._symbol_sync, symbol)
        if info is None:
            raise LookupError(f"Unknown MT5 symbol: {symbol}")
        return info

    # ------------------------------------------------------------- history

    def _rates_settled(self, mt5_name: str, tf: int, start: datetime, end: datetime) -> Any:
        """copy_rates_range, repeated while MT5 is still downloading history."""
        mt5 = self._mt5
        best = None
        best_len = -1
        for attempt in range(self._settings.history_settle_attempts):
            rates = mt5.copy_rates_range(mt5_name, tf, start, end)
            if rates is None:
                raise RuntimeError(f"MT5 history request failed for {mt5_name}: {mt5.last_error()}")
            if len(rates) == best_len:
                break
            best, best_len = rates, len(rates)
            if attempt + 1 < self._settings.history_settle_attempts:
                time.sleep(0.3)
        return best

    def _window_bars(
        self, mt5_name: str, timeframe: Timeframe, from_ts: int, to_ts: int, digits: int
    ) -> list[Trendbar]:
        mt5 = self._mt5
        mt5.symbol_select(mt5_name, True)
        rates = self._rates_settled(
            mt5_name,
            self._mt5_timeframe(timeframe),
            self._to_server_dt(from_ts),
            self._to_server_dt(to_ts),
        )
        bars: list[Trendbar] = []
        last_t = None
        for row in rates:
            t = self._bar_ms(row["time"])
            if t < from_ts or t > to_ts:
                continue
            if last_t is not None and t <= last_t:
                raise RuntimeError(f"MT5 returned out-of-order bars for {mt5_name}")
            last_t = t
            bars.append(
                Trendbar(
                    o=Decimal(str(round(float(row["open"]), digits))),
                    h=Decimal(str(round(float(row["high"]), digits))),
                    l=Decimal(str(round(float(row["low"]), digits))),
                    c=Decimal(str(round(float(row["close"]), digits))),
                    v=self._volume(row),
                    t=t,
                    digits=digits,
                )
            )
        return bars

    def _windows(self, timeframe: Timeframe, from_ts: int, to_ts: int) -> list[tuple[int, int]]:
        span = HISTORY_WINDOW_BARS * TIMEFRAME_MINUTES[timeframe] * 60_000
        windows = []
        start = from_ts
        while start <= to_ts:
            end = min(to_ts, start + span - 1)
            windows.append((start, end))
            start = end + 1
        return windows

    async def stream_trendbars(
        self,
        account_id: AccountId,
        symbol: str,
        timeframe: Timeframe,
        from_ts: int,
        to_ts: int | None,
        limit: int | None,
    ) -> AsyncIterator[Trendbar]:
        info = await self._require_symbol(symbol)
        _, mt5_name = self._resolve(symbol)
        now_ms = int(time.time() * 1000)
        end = now_ms if to_ts is None else min(to_ts, now_ms)
        if limit is not None:
            # A limit keeps the most recent bars of the interval.
            for bar in await self.get_trendbars(account_id, symbol, timeframe, from_ts, end, limit):
                yield bar
            return
        for w_start, w_end in self._windows(timeframe, from_ts, end):
            bars = await self._call(
                self._window_bars, mt5_name, timeframe, w_start, w_end, info.digits
            )
            for bar in bars:
                yield bar

    async def get_trendbars(
        self,
        account_id: AccountId,
        symbol: str,
        timeframe: Timeframe,
        from_ts: int,
        to_ts: int | None,
        limit: int | None,
    ) -> list[Trendbar]:
        info = await self._require_symbol(symbol)
        _, mt5_name = self._resolve(symbol)
        now_ms = int(time.time() * 1000)
        end = now_ms if to_ts is None else min(to_ts, now_ms)
        bars: list[Trendbar] = []
        for w_start, w_end in self._windows(timeframe, from_ts, end):
            bars.extend(
                await self._call(
                    self._window_bars, mt5_name, timeframe, w_start, w_end, info.digits
                )
            )
        if limit is not None:
            bars = bars[-limit:]
        return bars

    # ------------------------------------------------------------- live streams

    async def register_tick_handler(
        self, account_id: int, symbol: str, handler: TickHandler
    ) -> TickSubscription:
        info = await self._require_symbol(symbol)
        alias, mt5_name = self._resolve(symbol)
        token = str(uuid.uuid4())
        async with self._lock:
            state = self._tick_states.get(alias)
            if state is None:
                state = _TickState(mt5_name=mt5_name, alias=alias, digits=info.digits)
                self._tick_states[alias] = state
            state.handlers[token] = handler
        return TickSubscription(
            account_id=account_id, symbol=alias, symbol_id=info.symbol_id, token=token
        )

    async def unregister_tick_handler(self, subscription: TickSubscription) -> None:
        async with self._lock:
            state = self._tick_states.get(subscription.symbol)
            if state is None:
                return
            state.handlers.pop(subscription.token, None)
            if not state.handlers:
                self._tick_states.pop(subscription.symbol, None)

    async def register_trendbar_handler(
        self, account_id: int, symbol: str, timeframe: Timeframe, handler: TrendbarHandler
    ) -> TrendbarSubscription:
        info = await self._require_symbol(symbol)
        alias, mt5_name = self._resolve(symbol)
        token = str(uuid.uuid4())
        key = (alias, timeframe.value)
        async with self._lock:
            state = self._bar_states.get(key)
            if state is None:
                state = _BarState(
                    mt5_name=mt5_name, alias=alias, timeframe=timeframe, digits=info.digits
                )
                self._bar_states[key] = state
            state.handlers[token] = handler
        return TrendbarSubscription(
            account_id=account_id,
            symbol=alias,
            symbol_id=info.symbol_id,
            timeframe=timeframe,
            token=token,
        )

    async def unregister_trendbar_handler(self, subscription: TrendbarSubscription) -> None:
        key = (subscription.symbol, subscription.timeframe.value)
        async with self._lock:
            state = self._bar_states.get(key)
            if state is None:
                return
            state.handlers.pop(subscription.token, None)
            if not state.handlers:
                self._bar_states.pop(key, None)

    async def _poll_loop(self) -> None:
        interval = self._settings.poll_interval_seconds
        while not self._shutting_down:
            started = time.monotonic()
            try:
                if not self._connected:
                    await self._call(self._initialize)
                    self._connected = True
                    logger.info("Reconnected to MetaTrader 5")
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._connected:
                    logger.exception("MT5 polling failed; will reconnect")
                self._mark_disconnected()
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
                continue
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))

    def _mark_disconnected(self) -> None:
        self._connected = False
        # A new continuity tells consumers that live delivery was interrupted.
        self._continuity = "v1:" + uuid.uuid4().hex
        for state in self._bar_states.values():
            state.current = None

    async def _poll_once(self) -> None:
        async with self._lock:
            tick_states = list(self._tick_states.values())
            bar_states = list(self._bar_states.values())
        continuity = self._continuity
        tick_events, bar_events = await self._call(self._collect, tick_states, bar_states)
        if continuity != self._continuity:
            return
        for state, ticks in tick_events:
            for tick in ticks:
                await self._dispatch(list(state.handlers.values()), tick)
        for state, bars in bar_events:
            for bar in bars:
                await self._dispatch(list(state.handlers.values()), bar)

    @staticmethod
    async def _dispatch(handlers: list[Callable[[Any], Awaitable[None]]], item: Any) -> None:
        for handler in handlers:
            try:
                await handler(item)
            except Exception:
                logger.exception("Live MT5 handler failed")

    def _collect(
        self, tick_states: list[_TickState], bar_states: list[_BarState]
    ) -> tuple[list[tuple[_TickState, list[Tick]]], list[tuple[_BarState, list[Trendbar]]]]:
        """Runs on the MT5 thread: gather new ticks and changed bars."""
        mt5 = self._mt5
        terminal = mt5.terminal_info()
        if terminal is None or not terminal.connected:
            raise RuntimeError("MT5 terminal is not connected to the broker")
        tick_events = [(s, self._new_ticks(s)) for s in tick_states]
        bar_events = [(s, self._changed_bars(s)) for s in bar_states]
        return tick_events, bar_events

    def _anchor_ticks(self, state: _TickState) -> None:
        """Start a tick stream from now; earlier ticks are history, not live data."""
        mt5 = self._mt5
        latest = mt5.symbol_info_tick(state.mt5_name)
        if latest is None:
            return
        # Count ticks already stamped with the anchor millisecond so that a later
        # tick in that same millisecond is still delivered.
        anchor = int(latest.time_msc)
        existing = mt5.copy_ticks_from(
            state.mt5_name, anchor // 1000, TICKS_PER_POLL, mt5.COPY_TICKS_ALL
        )
        rows = existing if existing is not None else ()
        state.last_msc = anchor
        state.seen_at_last_msc = sum(1 for r in rows if int(r["time_msc"]) == anchor)

    def _new_ticks(self, state: _TickState) -> list[Tick]:
        mt5 = self._mt5
        if state.last_msc is None:
            self._anchor_ticks(state)
            return []
        from_seconds = state.last_msc // 1000
        raw = mt5.copy_ticks_from(state.mt5_name, from_seconds, TICKS_PER_POLL, mt5.COPY_TICKS_ALL)
        if raw is None:
            raise RuntimeError(f"MT5 tick request failed for {state.mt5_name}: {mt5.last_error()}")
        ticks: list[Tick] = []
        seen_same = 0
        for row in raw:
            msc = int(row["time_msc"])
            if msc < state.last_msc:
                continue
            if msc == state.last_msc:
                seen_same += 1
                if seen_same <= state.seen_at_last_msc:
                    continue
            bid, ask = float(row["bid"]), float(row["ask"])
            if bid <= 0 or ask <= 0:
                continue
            ticks.append(Tick(b=bid, a=ask, t=self._tick_ms(msc), digits=state.digits))
        if len(raw):
            newest = int(raw[-1]["time_msc"])
            count_newest = sum(1 for r in raw if int(r["time_msc"]) == newest)
            if newest == state.last_msc:
                state.seen_at_last_msc = max(state.seen_at_last_msc, count_newest)
            else:
                state.last_msc = newest
                state.seen_at_last_msc = count_newest
        return ticks

    def _changed_bars(self, state: _BarState) -> list[Trendbar]:
        mt5 = self._mt5
        rates = mt5.copy_rates_from_pos(state.mt5_name, self._mt5_timeframe(state.timeframe), 0, 2)
        if rates is None:
            raise RuntimeError(f"MT5 bar request failed for {state.mt5_name}: {mt5.last_error()}")
        out: list[Trendbar] = []
        rows = [
            (
                int(r["time"]),
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                self._volume(r),
            )
            for r in rates
        ]
        if not rows:
            return out
        newest = rows[-1]
        if state.current is not None and newest[0] > state.current[0]:
            # A new bar opened: publish the final version of the bar that just closed.
            closed = next((r for r in rows if r[0] == state.current[0]), None)
            if closed is not None and closed != state.current:
                out.append(self._to_trendbar(closed, state.digits))
        if newest != state.current:
            out.append(self._to_trendbar(newest, state.digits))
            state.current = newest
        return out

    def _to_trendbar(self, row: tuple, digits: int) -> Trendbar:
        t, o, h, l, c, v = row  # noqa: E741
        return Trendbar(
            o=Decimal(str(round(o, digits))),
            h=Decimal(str(round(h, digits))),
            l=Decimal(str(round(l, digits))),
            c=Decimal(str(round(c, digits))),
            v=int(v),
            t=self._bar_ms(t),
            digits=digits,
            continuity=self._continuity,
        )

    # ------------------------------------------------------------- trading (disabled)

    async def list_accounts(self) -> list[Account]:
        def run() -> list[Account]:
            info = self._mt5.account_info()
            if info is None:
                return []
            return [
                Account(
                    broker_name=str(info.company),
                    account_id=0,
                    trader_login=None,  # not exposed on purpose
                    balance=Decimal(str(info.balance)),
                    leverage=int(info.leverage),
                    is_live=info.trade_mode != ACCOUNT_TRADE_MODE_DEMO,
                    access_rights="NO_TRADING",
                )
            ]

        return await self._call(run)

    async def get_open_orders(self, account_id: AccountId) -> list[Order]:
        return []

    async def get_order_history(
        self, account_id: AccountId, from_ts: int | None = None, to_ts: int | None = None
    ) -> list[Order]:
        return []

    async def place_order(self, account_id: AccountId, order: Mapping[str, Any]) -> dict[str, Any]:
        raise TradingDisabledError("Trading is disabled: the MT5 bridge is read-only")

    async def cancel_order(self, account_id: AccountId, order_id: OrderId) -> None:
        raise TradingDisabledError("Trading is disabled: the MT5 bridge is read-only")

    async def get_open_positions(self, account_id: AccountId) -> list[Position]:
        return []

    async def get_deal_history(
        self, account_id: AccountId, from_ts: int | None = None, to_ts: int | None = None
    ) -> list[Deal]:
        return []

    async def close_position(
        self, account_id: AccountId, position_id: PositionId, close_volume: int | None = None
    ) -> Position:
        raise TradingDisabledError("Trading is disabled: the MT5 bridge is read-only")
