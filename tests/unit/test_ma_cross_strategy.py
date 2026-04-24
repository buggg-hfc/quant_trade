"""Tests for MACrossStrategy logic (no Rust engine needed)."""
import pytest
from src.strategy.examples.ma_cross import MACrossStrategy
from src.core.object import BarData


def _bar(close: float, sym: str = "TEST") -> BarData:
    return BarData(symbol=sym, symbol_id=0, datetime=0,
                   open=close, high=close + 1, low=close - 1, close=close, volume=1000)


def _feed_bars(strategy: MACrossStrategy, prices: list[float]) -> list[dict]:
    """Feed a list of prices and collect all orders emitted."""
    orders = []
    for p in prices:
        strategy.on_bar(_bar(p))
        orders.extend(strategy._pop_orders())
    return orders


class TestMACrossStrategy:
    def test_no_orders_before_warmup(self):
        s = MACrossStrategy(fast_period=3, slow_period=5)
        s.on_init()
        # Feed only slow_period - 1 bars → not enough history
        orders = _feed_bars(s, [100.0] * 4)
        assert orders == []

    def test_golden_cross_emits_buy(self):
        s = MACrossStrategy(fast_period=3, slow_period=5, trade_volume=100.0)
        s.on_init()
        # Flat prices then a sharp rise → golden cross
        prices = [100.0] * 5 + [110.0, 120.0, 130.0]
        orders = _feed_bars(s, prices)
        buys = [o for o in orders if o["direction"] == "LONG"]
        assert len(buys) >= 1

    def test_death_cross_emits_sell(self):
        s = MACrossStrategy(fast_period=3, slow_period=5, trade_volume=100.0)
        s.on_init()
        # Rising then falling
        prices = [100.0] * 5 + [115.0, 120.0, 125.0] + [100.0, 90.0, 80.0]
        orders = _feed_bars(s, prices)
        sells = [o for o in orders if o["direction"] == "SHORT"]
        assert len(sells) >= 1

    def test_param_override(self):
        s = MACrossStrategy(fast_period=10, slow_period=30)
        assert s.fast_period == 10
        assert s.slow_period == 30
