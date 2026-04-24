"""BaseStrategy: abstract base for all strategies.

Lifecycle: on_init → on_bar (per bar) → on_trade (per fill) → on_stop
Buy/sell emit OrderRequest dicts consumed by BacktestEngine or a Gateway.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from src.core.object import BarData, TradeData, OrderData, PositionData, AccountData


class BaseStrategy(ABC):
    """
    Subclass convention:
    - Class-level int/float attributes are treated as GUI-editable parameters.
    - Call self.buy() / self.sell() inside on_bar() to emit orders.
    - self.positions and self.account are updated by the engine between bars.
    """

    def __init__(self, **params):
        # Apply parameter overrides (e.g., from optimizer)
        for k, v in params.items():
            if hasattr(self, k):
                setattr(self, k, v)

        # Injected by engine before first bar
        self._positions: dict[str, PositionData] = {}
        self._account: AccountData = AccountData(balance=0.0, available=0.0)
        self._pending_orders: list[dict] = []

    # ── Hooks (override in subclass) ──────────────────────────────────────────

    def on_init(self) -> None:
        """Called once before the first bar. Load history, pre-compute indicators."""

    @abstractmethod
    def on_bar(self, bar: BarData) -> None:
        """Called for every bar. Emit orders via self.buy() / self.sell()."""

    def on_trade(self, trade: TradeData) -> None:
        """Called after each fill. Update internal state if needed."""

    def on_stop(self) -> None:
        """Called after the last bar (backtest) or on shutdown (live)."""

    # ── Order helpers ─────────────────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        price: float,
        volume: float,
        order_type: str = "LIMIT",
    ) -> str:
        oid = str(uuid.uuid4())
        self._pending_orders.append({
            "order_id": oid,
            "symbol": symbol,
            "direction": "LONG",
            "order_type": order_type,
            "price": price,
            "volume": volume,
        })
        return oid

    def sell(
        self,
        symbol: str,
        price: float,
        volume: float,
        order_type: str = "LIMIT",
    ) -> str:
        oid = str(uuid.uuid4())
        self._pending_orders.append({
            "order_id": oid,
            "symbol": symbol,
            "direction": "SHORT",
            "order_type": order_type,
            "price": price,
            "volume": volume,
        })
        return oid

    def _pop_orders(self) -> list[dict]:
        orders, self._pending_orders = self._pending_orders, []
        return orders

    # ── State accessors (injected by engine) ──────────────────────────────────

    @property
    def positions(self) -> dict[str, PositionData]:
        return self._positions

    @property
    def account(self) -> AccountData:
        return self._account

    def get_pos(self, symbol: str) -> float:
        """Signed net volume for symbol (positive = long, negative = short, 0 = flat)."""
        p = self._positions.get(symbol)
        return p.net_volume if p else 0.0
