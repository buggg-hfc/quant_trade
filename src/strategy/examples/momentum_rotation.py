"""Multi-asset momentum rotation strategy.

At each rebalance interval the strategy ranks symbols by N-day momentum and
holds the top-K, equal-weighted. Exits symbols that drop out of the top-K.

Works with multi-symbol BacktestEngine input.
"""
from __future__ import annotations

from collections import defaultdict, deque

from src.strategy.base import BaseStrategy
from src.core.object import BarData


class MomentumRotationStrategy(BaseStrategy):
    lookback: int = 20          # momentum lookback (bars)
    top_k: int = 2              # number of symbols to hold
    rebalance_every: int = 5    # rebalance every N bars
    trade_volume: float = 100.0

    def on_init(self) -> None:
        self._closes: defaultdict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.lookback + 1)
        )
        self._bar_count: int = 0
        self._held: set[str] = set()

    def on_bar(self, bar: BarData) -> None:
        self._closes[bar.symbol].append(bar.close)
        self._bar_count += 1

        if self._bar_count % self.rebalance_every != 0:
            return

        # Compute momentum for each symbol that has enough history
        scores: dict[str, float] = {}
        for sym, buf in self._closes.items():
            if len(buf) > self.lookback:
                scores[sym] = buf[-1] / buf[0] - 1.0  # simple rate of change

        if not scores:
            return

        ranked = sorted(scores, key=scores.__getitem__, reverse=True)
        target = set(ranked[: self.top_k])

        # Exit symbols no longer in top-K
        for sym in self._held - target:
            pos = self.get_pos(sym)
            if pos > 0:
                self.sell(sym, self._closes[sym][-1], pos)
            elif pos < 0:
                self.buy(sym, self._closes[sym][-1], abs(pos))

        # Enter new top-K symbols
        for sym in target - self._held:
            self.buy(sym, self._closes[sym][-1], self.trade_volume)

        self._held = target
