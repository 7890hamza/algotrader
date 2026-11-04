"""Order and position commands for the MT5 bridge (demo accounts only, opt-in).

Off unless the bridge is started with ``MT5_TRADING_ENABLED=true``, and even then it
refuses any account that is not a demo account. All functions run on the bridge's MT5
worker thread and take the ``MetaTrader5`` module as ``mt5``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Mapping

from app.domain.models import Order, Position
from app.domain.models.position import TradeData

MAGIC = 20261103
COMMENT = "AlgoTrader"
DEVIATION_POINTS = 10
ACCOUNT_TRADE_MODE_DEMO = 0
OK_RETCODES = {10008, 10009}  # placed, done

# MetaTrader5 constants, with their documented values as fallbacks.
_C = {
    "TRADE_ACTION_DEAL": 1,
    "TRADE_ACTION_PENDING": 5,
    "TRADE_ACTION_REMOVE": 8,
    "ORDER_TYPE_BUY": 0,
    "ORDER_TYPE_SELL": 1,
    "ORDER_TYPE_BUY_LIMIT": 2,
    "ORDER_TYPE_SELL_LIMIT": 3,
    "ORDER_TYPE_BUY_STOP": 4,
    "ORDER_TYPE_SELL_STOP": 5,
    "ORDER_TIME_GTC": 0,
    "ORDER_FILLING_FOK": 0,
    "ORDER_FILLING_IOC": 1,
    "ORDER_FILLING_RETURN": 2,
    "POSITION_TYPE_BUY": 0,
}
BUY_TYPES = {0, 2, 4, 6}
TYPE_NAMES = {
    0: "MARKET",
    1: "MARKET",
    2: "LIMIT",
    3: "LIMIT",
    4: "STOP",
    5: "STOP",
    6: "STOP_LIMIT",
    7: "STOP_LIMIT",
}


class TradingDisabledError(RuntimeError):
    """Trading is off, or the account is not a demo account."""


class OrderRejectedError(RuntimeError):
    """MT5 refused the order; the message carries its return code and reason."""


def const(mt5: Any, name: str) -> int:
    return int(getattr(mt5, name, _C[name]))


def ensure_trading(mt5: Any, enabled: bool) -> None:
    if not enabled:
        raise TradingDisabledError(
            "Trading is off. Start the bridge with scripts\\windows\\mt5-broker-trading.bat "
            "to send orders to your demo account."
        )
    account = mt5.account_info()
    if account is None:
        raise TradingDisabledError("MT5 is not logged in.")
    if account.trade_mode != ACCOUNT_TRADE_MODE_DEMO:
        raise TradingDisabledError("Orders are only allowed on a demo account.")


def _filling(mt5: Any, mt5_name: str) -> int:
    info = mt5.symbol_info(mt5_name)
    mode = int(getattr(info, "filling_mode", 0) or 0)
    if mode & 1:
        return const(mt5, "ORDER_FILLING_FOK")
    if mode & 2:
        return const(mt5, "ORDER_FILLING_IOC")
    return const(mt5, "ORDER_FILLING_RETURN")


def _send(mt5: Any, request: dict[str, Any]) -> Any:
    result = mt5.order_send(request)
    if result is None:
        raise OrderRejectedError(f"MT5 did not accept the request: {mt5.last_error()}")
    if int(result.retcode) not in OK_RETCODES:
        raise OrderRejectedError(f"MT5 rejected the order ({result.retcode}): {result.comment}")
    return result


def place_order(mt5: Any, mt5_name: str, order: Mapping[str, Any]) -> dict[str, Any]:
    """Market, limit or stop order with optional stop loss / take profit."""
    if not mt5.symbol_select(mt5_name, True):
        raise OrderRejectedError(f"MT5 does not know the symbol {mt5_name}.")
    buy = order["tradeSide"] == "BUY"
    kind = order["orderType"]
    volume = float(order["volume"])
    if volume <= 0:
        raise OrderRejectedError("Volume must be at least 1.")
    request: dict[str, Any] = {
        "symbol": mt5_name,
        "volume": volume,
        "magic": MAGIC,
        "comment": str(order.get("comment") or COMMENT)[:31],
        "deviation": DEVIATION_POINTS,
    }
    if order.get("stopLoss") is not None:
        request["sl"] = float(order["stopLoss"])
    if order.get("takeProfit") is not None:
        request["tp"] = float(order["takeProfit"])
    if kind == "MARKET":
        tick = mt5.symbol_info_tick(mt5_name)
        if tick is None:
            raise OrderRejectedError("No live price for this symbol.")
        request.update(
            action=const(mt5, "TRADE_ACTION_DEAL"),
            type=const(mt5, "ORDER_TYPE_BUY" if buy else "ORDER_TYPE_SELL"),
            price=float(tick.ask if buy else tick.bid),
            type_filling=_filling(mt5, mt5_name),
        )
    elif kind in ("LIMIT", "STOP"):
        price = order.get("limitPrice") if kind == "LIMIT" else order.get("stopPrice")
        if price is None:
            raise OrderRejectedError(f"A {kind.lower()} order needs a price.")
        side = "BUY" if buy else "SELL"
        request.update(
            action=const(mt5, "TRADE_ACTION_PENDING"),
            type=const(mt5, f"ORDER_TYPE_{side}_{kind}"),
            price=float(price),
            type_time=const(mt5, "ORDER_TIME_GTC"),
            type_filling=const(mt5, "ORDER_FILLING_RETURN"),
        )
    else:
        raise OrderRejectedError(f"Order type {kind} is not supported.")
    result = _send(mt5, request)
    return {
        "orderId": int(result.order),
        "dealId": int(getattr(result, "deal", 0) or 0),
        "price": float(getattr(result, "price", 0) or request.get("price", 0)),
        "volume": float(getattr(result, "volume", volume) or volume),
        "retcode": int(result.retcode),
        "comment": str(getattr(result, "comment", "")),
    }


def cancel_order(mt5: Any, ticket: int) -> None:
    _send(mt5, {"action": const(mt5, "TRADE_ACTION_REMOVE"), "order": int(ticket)})


def close_position(
    mt5: Any, ticket: int, volume: float | None, alias_of: Callable[[str], str]
) -> Position:
    found = mt5.positions_get(ticket=int(ticket))
    if not found:
        raise OrderRejectedError(f"No open position {ticket}.")
    p = found[0]
    buy = int(p.type) == const(mt5, "POSITION_TYPE_BUY")
    tick = mt5.symbol_info_tick(p.symbol)
    if tick is None:
        raise OrderRejectedError("No live price to close at.")
    _send(
        mt5,
        {
            "action": const(mt5, "TRADE_ACTION_DEAL"),
            "symbol": p.symbol,
            "volume": float(volume or p.volume),
            "type": const(mt5, "ORDER_TYPE_SELL" if buy else "ORDER_TYPE_BUY"),
            "position": int(ticket),
            "price": float(tick.bid if buy else tick.ask),
            "deviation": DEVIATION_POINTS,
            "magic": MAGIC,
            "comment": COMMENT,
            "type_filling": _filling(mt5, p.symbol),
        },
    )
    return to_position(p, alias_of, status="CLOSED")


def _dec(value: Any) -> Decimal | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return Decimal(str(v)) if v else None


def to_position(p: Any, alias_of: Callable[[str], str], status: str = "OPEN") -> Position:
    alias = alias_of(str(p.symbol))
    return Position(
        position_id=int(p.ticket),
        trade_data=TradeData(
            symbol_id=0,
            volume=int(round(float(p.volume))),
            trade_side="BUY" if int(p.type) == 0 else "SELL",
            open_timestamp=int(getattr(p, "time_msc", 0) or 0),
            comment=str(getattr(p, "comment", "") or "") or None,
        ),
        position_status=status,
        swap=int(round(float(getattr(p, "swap", 0) or 0))),
        price=_dec(p.price_open),
        stop_loss=_dec(getattr(p, "sl", 0)),
        take_profit=_dec(getattr(p, "tp", 0)),
        symbol=alias,
        current_price=_dec(getattr(p, "price_current", 0)),
        profit=Decimal(str(float(getattr(p, "profit", 0) or 0))),
    )


def to_order(o: Any, alias_of: Callable[[str], str]) -> Order:
    kind = TYPE_NAMES.get(int(o.type), str(o.type))
    price = _dec(o.price_open)
    return Order(
        order_id=int(o.ticket),
        trade_data=TradeData(
            symbol_id=0,
            volume=int(round(float(o.volume_current))),
            trade_side="BUY" if int(o.type) in BUY_TYPES else "SELL",
            open_timestamp=int(getattr(o, "time_setup_msc", 0) or 0),
            comment=str(getattr(o, "comment", "") or "") or None,
        ),
        order_type=kind,
        order_status="ACCEPTED",
        limit_price=price if kind == "LIMIT" else None,
        stop_price=price if kind in ("STOP", "STOP_LIMIT") else None,
        stop_loss=_dec(getattr(o, "sl", 0)),
        take_profit=_dec(getattr(o, "tp", 0)),
        symbol=alias_of(str(o.symbol)),
    )
