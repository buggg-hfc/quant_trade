"""Tests for BaseStrategy."""
import pytest
from src.strategy.base import BaseStrategy
from src.core.object import BarData


class SimpleStrategy(BaseStrategy):
    threshold: float = 100.0

    def on_bar(self, bar: BarData) -> None:
        if bar.close > self.threshold and self.get_pos(bar.symbol) == 0:
            self.buy(bar.symbol, bar.close, 10.0)
        elif bar.close <= self.threshold and self.get_pos(bar.symbol) > 0:
            self.sell(bar.symbol, bar.close, self.get_pos(bar.symbol))


def _bar(close: float, sym: str = "TEST") -> BarData:
    return BarData(symbol=sym, symbol_id=0, datetime=0,
                   open=close, high=close, low=close, close=close, volume=1000)


class TestBaseStrategy:
    def test_param_override(self):
        s = SimpleStrategy(threshold=200.0)
        assert s.threshold == 200.0

    def test_buy_emits_order(self):
        s = SimpleStrategy()
        bar = _bar(150.0)
        s.on_bar(bar)
        orders = s._pop_orders()
        assert len(orders) == 1
        assert orders[0]["direction"] == "LONG"
        assert orders[0]["volume"] == 10.0

    def test_pop_orders_clears_queue(self):
        s = SimpleStrategy()
        s.on_bar(_bar(150.0))
        s._pop_orders()
        assert s._pop_orders() == []

    def test_sell_emits_short_order(self):
        s = SimpleStrategy()
        s.sell("TEST", 100.0, 5.0)
        orders = s._pop_orders()
        assert orders[0]["direction"] == "SHORT"

    def test_get_pos_default_zero(self):
        s = SimpleStrategy()
        assert s.get_pos("UNKNOWN") == 0.0

    def test_positions_updated_externally(self):
        from src.core.object import PositionData
        s = SimpleStrategy()
        s._positions["TEST"] = PositionData(symbol="TEST", net_volume=50.0)
        assert s.get_pos("TEST") == 50.0
