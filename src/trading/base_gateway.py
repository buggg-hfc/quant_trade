"""Abstract Gateway interface + lightweight OMS (Order Management System).

Every concrete gateway (Paper, CTP, XTP, Crypto) inherits BaseGateway and
implements the abstract methods. The embedded OrderBook handles order
lifecycle state transitions so each gateway doesn't have to re-implement them.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.core.object import (
    OrderData, TradeData, TickData, BarData, AccountData, PositionData,
)

logger = logging.getLogger(__name__)


# ── Order request ─────────────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    symbol: str
    direction: str        # "LONG" | "SHORT"
    order_type: str       # "LIMIT" | "MARKET"
    price: float
    volume: float
    order_id: str = ""    # filled by gateway on submission


# ── OMS ───────────────────────────────────────────────────────────────────────

# Valid state transitions
_TRANSITIONS: dict[str, set[str]] = {
    "SUBMITTED":  {"ACCEPTED", "REJECTED"},
    "ACCEPTED":   {"PARTIAL", "FILLED", "CANCELLED"},
    "PARTIAL":    {"FILLED", "CANCELLED"},
    "FILLED":     set(),
    "CANCELLED":  set(),
    "REJECTED":   set(),
}


class OrderBook:
    """Tracks live order state. Thread-safe for single-threaded event loops."""

    def __init__(self) -> None:
        self._orders: dict[str, OrderData] = {}

    def add(self, order: OrderData) -> None:
        self._orders[order.order_id] = order

    def transition(self, order_id: str, new_status: str, filled_vol: float = 0.0) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            logger.warning(f"OrderBook: unknown order_id {order_id}")
            return False
        if new_status not in _TRANSITIONS.get(order.status, set()):
            logger.warning(
                f"Invalid transition {order.status} → {new_status} for {order_id}"
            )
            return False
        order.status = new_status
        if filled_vol:
            order.filled += filled_vol
        return True

    def get(self, order_id: str) -> Optional[OrderData]:
        return self._orders.get(order_id)

    def open_orders(self) -> list[OrderData]:
        return [o for o in self._orders.values() if o.status in ("SUBMITTED", "ACCEPTED", "PARTIAL")]

    def all_orders(self) -> list[OrderData]:
        return list(self._orders.values())


# ── Abstract gateway ──────────────────────────────────────────────────────────

class BaseGateway(ABC):
    """
    Subclass contract:
    - Call self._on_order(order) whenever order status changes.
    - Call self._on_trade(trade) whenever a fill occurs.
    - Call self._on_tick(tick) for every incoming market tick.
    - Call self._on_bar(bar)  for synthesised bar events.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.order_book = OrderBook()
        self._on_order_cb: list[Callable[[OrderData], None]] = []
        self._on_trade_cb: list[Callable[[TradeData], None]] = []
        self._on_tick_cb:  list[Callable[[TickData],  None]] = []
        self._on_bar_cb:   list[Callable[[BarData],   None]] = []

    # ── Abstract ──────────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None: ...

    @abstractmethod
    def send_order(self, req: OrderRequest) -> str:
        """Submit order; return order_id string."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    def query_account(self) -> AccountData: ...

    @abstractmethod
    def query_position(self, symbol: str) -> PositionData: ...

    # ── Callback registration ─────────────────────────────────────────────────

    def on_order(self, fn: Callable[[OrderData], None]) -> None:
        self._on_order_cb.append(fn)

    def on_trade(self, fn: Callable[[TradeData], None]) -> None:
        self._on_trade_cb.append(fn)

    def on_tick(self, fn: Callable[[TickData], None]) -> None:
        self._on_tick_cb.append(fn)

    def on_bar(self, fn: Callable[[BarData], None]) -> None:
        self._on_bar_cb.append(fn)

    # ── Dispatch helpers (called by subclasses) ───────────────────────────────

    def _on_order(self, order: OrderData) -> None:
        for cb in self._on_order_cb:
            cb(order)

    def _on_trade(self, trade: TradeData) -> None:
        for cb in self._on_trade_cb:
            cb(trade)

    def _on_tick(self, tick: TickData) -> None:
        for cb in self._on_tick_cb:
            cb(tick)

    def _on_bar(self, bar: BarData) -> None:
        for cb in self._on_bar_cb:
            cb(bar)
