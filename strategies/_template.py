"""Strategy template — copy this file, rename the class, fill in on_bar().

Class-level int/float attributes are auto-detected as GUI-editable parameters.
"""
from src.strategy.base import BaseStrategy
from src.core.object import BarData


class MyStrategy(BaseStrategy):
    # ── Parameters (GUI will show these as editable fields) ──────────────────
    fast_period: int = 5
    slow_period: int = 20
    trade_volume: float = 100.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_init(self) -> None:
        """Called once before the first bar. Pre-compute indicators here."""
        pass

    def on_bar(self, bar: BarData) -> None:
        """Called for every bar. Emit orders via self.buy() / self.sell()."""
        # Example: buy on the first bar, do nothing else
        if self.get_pos(bar.symbol) == 0:
            self.buy(bar.symbol, bar.close, self.trade_volume)

    def on_stop(self) -> None:
        """Called after the last bar. Clean up if needed."""
        pass
