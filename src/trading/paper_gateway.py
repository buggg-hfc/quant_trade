"""PaperGateway: simulated live trading using Rust SimBroker logic.

Intended use:
  - Default gateway when no live SDK is available.
  - Interface-identical to real gateways — swap paper→CTP/XTP with one config change.
  - Feed bars via process_bar() to trigger simulated matching.

Matching rules mirror BacktestEngine (same BrokerConfigPy defaults from settings.yaml):
  - Limit orders: filled at bar open if price condition met, else left pending.
  - Price-limit (涨跌停): long rejected at limit-up close, short at limit-down.
  - Commission + slippage applied.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from src.core.object import (
    OrderData, TradeData, TickData, BarData, AccountData, PositionData,
)
from src.trading.base_gateway import BaseGateway, OrderRequest
from src.utils.config import get_settings

logger = logging.getLogger(__name__)


class PaperGateway(BaseGateway):
    """Simulated gateway for paper trading and integration testing."""

    def __init__(self, initial_capital: Optional[float] = None) -> None:
        super().__init__("paper")
        cfg = get_settings()
        self._capital = initial_capital or cfg.backtest.initial_capital
        self._commission_rate = cfg.backtest.commission_rate
        self._slippage = cfg.backtest.slippage
        self._price_limit_pct = cfg.backtest.price_limit_pct

        self._cash: float = self._capital
        self._positions: dict[str, PositionData] = {}
        self._latest_price: dict[str, float] = {}
        self._trade_seq: int = 0

    # ── BaseGateway interface ──────────────────────────────────────────────────

    def connect(self) -> None:
        logger.info("PaperGateway connected")

    def disconnect(self) -> None:
        logger.info("PaperGateway disconnected")

    def subscribe(self, symbols: list[str]) -> None:
        for s in symbols:
            self._latest_price.setdefault(s, 0.0)

    def send_order(self, req: OrderRequest) -> str:
        oid = req.order_id or str(uuid.uuid4())
        order = OrderData(
            order_id=oid,
            symbol=req.symbol,
            direction=req.direction,
            order_type=req.order_type,
            price=req.price,
            volume=req.volume,
            status="SUBMITTED",
        )
        self.order_book.add(order)
        self.order_book.transition(oid, "ACCEPTED")
        self._on_order(order)
        return oid

    def cancel_order(self, order_id: str) -> None:
        order = self.order_book.get(order_id)
        if order and self.order_book.transition(order_id, "CANCELLED"):
            self._on_order(order)

    def query_account(self) -> AccountData:
        market_value = sum(
            pos.net_volume * self._latest_price.get(sym, 0.0)
            for sym, pos in self._positions.items()
        )
        balance = self._cash + market_value
        return AccountData(
            balance=balance,
            available=self._cash,
            total_pnl=balance - self._capital,
        )

    def query_position(self, symbol: str) -> PositionData:
        return self._positions.get(symbol, PositionData(symbol=symbol))

    # ── Bar-driven matching ────────────────────────────────────────────────────

    def process_bar(self, bar: BarData) -> None:
        """Feed a bar into the paper engine; pending orders are matched."""
        # Limit-up/down is relative to the previous bar's close (prev_close × ±pct)
        prev_close = self._latest_price.get(bar.symbol, bar.close)
        self._latest_price[bar.symbol] = bar.close

        limit_up   = prev_close * (1 + self._price_limit_pct)
        limit_down = prev_close * (1 - self._price_limit_pct)

        for order in list(self.order_book.open_orders()):
            if order.symbol != bar.symbol:
                continue

            # Price-limit: cancel pending orders that can't execute at the limit
            if order.direction == "LONG" and bar.close >= limit_up:
                self.order_book.transition(order.order_id, "CANCELLED")
                self._on_order(order)
                continue
            if order.direction == "SHORT" and bar.close <= limit_down:
                self.order_book.transition(order.order_id, "CANCELLED")
                self._on_order(order)
                continue

            # Matching: limit order fills at open if price condition met
            fill_price: Optional[float] = None
            if order.order_type == "MARKET":
                fill_price = bar.open * (1 + self._slippage if order.direction == "LONG" else 1 - self._slippage)
            elif order.order_type == "LIMIT":
                if order.direction == "LONG" and bar.open <= order.price:
                    fill_price = bar.open * (1 + self._slippage)
                elif order.direction == "SHORT" and bar.open >= order.price:
                    fill_price = bar.open * (1 - self._slippage)

            if fill_price is None:
                continue

            commission = fill_price * order.volume * self._commission_rate
            self._apply_fill(order, fill_price, order.volume, commission, bar.datetime)

        self._on_bar(bar)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply_fill(
        self,
        order: OrderData,
        fill_price: float,
        fill_vol: float,
        commission: float,
        ts: int,
    ) -> None:
        self._trade_seq += 1
        trade = TradeData(
            trade_id=str(self._trade_seq),
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            price=fill_price,
            volume=fill_vol,
            commission=commission,
            datetime=ts,
        )

        # Update cash
        if order.direction == "LONG":
            self._cash -= fill_price * fill_vol + commission
        else:
            self._cash += fill_price * fill_vol - commission

        # Update position
        pos = self._positions.setdefault(order.symbol, PositionData(symbol=order.symbol))
        if order.direction == "LONG":
            total_cost = pos.avg_price * pos.net_volume + fill_price * fill_vol
            pos.net_volume += fill_vol
            pos.avg_price = total_cost / pos.net_volume if pos.net_volume else 0.0
        else:
            pos.net_volume -= fill_vol
            if abs(pos.net_volume) < 1e-9:
                pos.avg_price = 0.0

        self.order_book.transition(order.order_id, "FILLED", fill_vol)
        self._on_order(order)
        self._on_trade(trade)
