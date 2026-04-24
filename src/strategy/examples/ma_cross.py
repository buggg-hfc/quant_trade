"""Dual moving-average crossover strategy (A-share single symbol)."""
from __future__ import annotations

from collections import deque

from src.strategy.base import BaseStrategy
from src.core.object import BarData


class MACrossStrategy(BaseStrategy):
    fast_period: int = 5
    slow_period: int = 20
    trade_volume: float = 100.0

    def on_init(self) -> None:
        self._fast: deque[float] = deque(maxlen=self.fast_period)
        self._slow: deque[float] = deque(maxlen=self.slow_period)
        self._prev_signal: int = 0   # +1 = fast > slow, -1 = fast < slow

    def on_bar(self, bar: BarData) -> None:
        self._fast.append(bar.close)
        self._slow.append(bar.close)

        if len(self._slow) < self.slow_period:
            return

        fast_ma = sum(self._fast) / len(self._fast)
        slow_ma = sum(self._slow) / len(self._slow)
        signal = 1 if fast_ma > slow_ma else -1

        pos = self.get_pos(bar.symbol)

        if signal == 1 and self._prev_signal != 1:
            # Golden cross → go long (close short first if any)
            if pos < 0:
                self.buy(bar.symbol, bar.close, abs(pos))
            if pos <= 0:
                self.buy(bar.symbol, bar.close, self.trade_volume)

        elif signal == -1 and self._prev_signal != -1:
            # Death cross → go short (close long first if any)
            if pos > 0:
                self.sell(bar.symbol, bar.close, pos)
            if pos >= 0:
                self.sell(bar.symbol, bar.close, self.trade_volume)

        self._prev_signal = signal
