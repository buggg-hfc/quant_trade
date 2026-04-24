"""Crypto grid strategy.

Places buy orders at equally spaced price levels below the reference price
and sell orders above. Each filled buy is paired with a sell one grid step
above; each filled sell is paired with a buy one step below.

Suitable for sideways / mean-reverting crypto markets.
"""
from __future__ import annotations

from src.strategy.base import BaseStrategy
from src.core.object import BarData, TradeData


class CryptoGridStrategy(BaseStrategy):
    grid_step_pct: float = 0.01   # distance between grid levels (1%)
    num_grids: int = 5            # levels above and below center
    lot_size: float = 0.01        # units per grid order (e.g., 0.01 BTC)

    def on_init(self) -> None:
        self._ref_price: float = 0.0
        self._initialized: bool = False

    def on_bar(self, bar: BarData) -> None:
        if not self._initialized:
            self._ref_price = bar.close
            self._place_initial_grid(bar.symbol, bar.close)
            self._initialized = True

    def _place_initial_grid(self, symbol: str, center: float) -> None:
        step = center * self.grid_step_pct
        for i in range(1, self.num_grids + 1):
            buy_price = center - i * step
            self.buy(symbol, buy_price, self.lot_size)

    def on_trade(self, trade: TradeData) -> None:
        step = self._ref_price * self.grid_step_pct
        if trade.direction == "LONG":
            # Pair with a sell one step above
            self.sell(trade.symbol, trade.price + step, trade.volume)
        else:
            # Pair with a buy one step below
            self.buy(trade.symbol, trade.price - step, trade.volume)
