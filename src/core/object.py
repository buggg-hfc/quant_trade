from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


class SymbolRegistry:
    """Thread-safe singleton: symbol string ↔ u32 ID bidirectional mapping.

    Rust Bar stores symbol_id (u32) to stay numpy-compatible (no variable-length fields).
    Python callers use this registry to convert before sending bars to Rust and after
    receiving callbacks.
    """

    _str_to_id: ClassVar[dict[str, int]] = {}
    _id_to_str: ClassVar[dict[int, str]] = {}

    @classmethod
    def get_or_register(cls, symbol: str) -> int:
        if symbol not in cls._str_to_id:
            sid = len(cls._str_to_id)
            cls._str_to_id[symbol] = sid
            cls._id_to_str[sid] = symbol
        return cls._str_to_id[symbol]

    @classmethod
    def lookup(cls, symbol_id: int) -> str:
        return cls._id_to_str[symbol_id]

    @classmethod
    def reset(cls) -> None:
        """Clear registry (for tests only)."""
        cls._str_to_id.clear()
        cls._id_to_str.clear()


@dataclass
class BarData:
    symbol: str
    symbol_id: int
    datetime: int        # Unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TickData:
    symbol: str
    symbol_id: int
    datetime: int
    last_price: float
    bid_price: float
    ask_price: float
    volume: float


@dataclass
class OrderData:
    order_id: str
    symbol: str
    direction: str       # "LONG" | "SHORT"
    order_type: str      # "LIMIT" | "MARKET"
    price: float
    volume: float
    filled: float = 0.0
    status: str = "SUBMITTED"
    datetime: int = 0


@dataclass
class TradeData:
    trade_id: str
    order_id: str
    symbol: str
    direction: str
    price: float
    volume: float
    commission: float
    datetime: int


@dataclass
class PositionData:
    symbol: str
    net_volume: float = 0.0
    avg_price: float = 0.0
    unrealized_pnl: float = 0.0


@dataclass
class AccountData:
    balance: float
    available: float
    frozen: float = 0.0
    total_pnl: float = 0.0
