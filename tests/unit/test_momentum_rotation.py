"""Tests for MomentumRotationStrategy logic."""
import pytest
from src.strategy.examples.momentum_rotation import MomentumRotationStrategy
from src.core.object import BarData


def _bar(sym: str, close: float, ts: int = 0) -> BarData:
    return BarData(symbol=sym, symbol_id=0, datetime=ts,
                   open=close, high=close, low=close, close=close, volume=1000)


class TestMomentumRotation:
    def test_no_orders_before_warmup(self):
        s = MomentumRotationStrategy(lookback=5, top_k=1, rebalance_every=5)
        s.on_init()
        orders = []
        for i in range(4):  # < lookback
            s.on_bar(_bar("A", 100 + i))
            orders.extend(s._pop_orders())
        assert orders == []

    def test_picks_top_performer(self):
        s = MomentumRotationStrategy(lookback=5, top_k=1, rebalance_every=5, trade_volume=10.0)
        s.on_init()
        # Feed 6 bars: A rises, B falls → A should be selected
        for i in range(6):
            s.on_bar(_bar("A", 100 + i * 2))  # rising
            s.on_bar(_bar("B", 100 - i))       # falling
        s._pop_orders()  # clear warmup noise

        # One more rebalance cycle
        for _ in range(5):
            s.on_bar(_bar("A", 115.0))
            s.on_bar(_bar("B", 94.0))

        orders = s._pop_orders()
        buy_syms = [o["symbol"] for o in orders if o["direction"] == "LONG"]
        assert "A" in buy_syms

    def test_rebalance_exits_loser(self):
        s = MomentumRotationStrategy(lookback=5, top_k=1, rebalance_every=5, trade_volume=10.0)
        s.on_init()
        from src.core.object import PositionData

        # Pre-populate price history to bypass warmup
        for i in range(6):
            s._closes["A"].append(100.0)         # flat  → momentum = 0
            s._closes["B"].append(100 + i * 3)  # rising → momentum > 0

        # Simulate already holding A
        s._held = {"A"}
        s._positions["A"] = PositionData(symbol="A", net_volume=10.0)

        # Feed exactly rebalance_every bars to trigger one rebalance
        for _ in range(5):
            s.on_bar(_bar("A", 100.0))

        orders = s._pop_orders()
        sell_syms = [o["symbol"] for o in orders if o["direction"] == "SHORT"]
        assert "A" in sell_syms
