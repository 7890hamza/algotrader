from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Symbol:
    symbol_id: int
    symbol_name: str
    digits: int
    pip_position: int
    commission: int = 0
    commission_type: str | None = None
    # Contract math for risk tools: price step, money per step, and its currency.
    tick_size: float | None = None
    tick_value: float | None = None
    contract_size: float | None = None
    currency: str | None = None
