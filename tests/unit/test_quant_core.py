"""Smoke tests for the quant_core Rust extension."""
import pytest
from quant_core import Bar, BacktestMetrics, BacktestRunner, BrokerConfigPy, EventEngine


def make_config(**overrides) -> BrokerConfigPy:
    defaults = dict(
        commission_rate=0.0003,
        slippage=0.001,
        price_limit_pct=0.10,
        initial_capital=100_000.0,
        max_position_pct=0.9,
        daily_loss_limit=0.10,
        max_order_volume=10_000.0,
    )
    defaults.update(overrides)
    return BrokerConfigPy(**defaults)


def test_bar_creation():
    bar = Bar(0, 1000, 10.0, 11.0, 9.5, 10.5, 500.0)
    assert bar.symbol_id == 0
    assert bar.open == 10.0
    assert bar.close == 10.5
    assert bar.volume == 500.0


def test_event_engine_start_stop():
    engine = EventEngine()
    engine.start()
    engine.stop()


def test_backtest_runner_no_trades():
    """Strategy that never sends orders should return zero-trade metrics."""
    calls = {"bar": 0}

    def on_bar(bar):
        calls["bar"] += 1
        return []  # no orders

    def on_trade(*args):
        pass

    cfg = make_config()
    runner = BacktestRunner(cfg, on_bar, on_trade)
    bars = [Bar(0, i * 86400, 10.0 + i * 0.01, 10.5 + i * 0.01,
                9.8 + i * 0.01, 10.2 + i * 0.01, 1000.0)
            for i in range(10)]
    metrics = runner.run_batch(bars)
    assert calls["bar"] == 10
    assert metrics.total_trades == 0
    assert metrics.total_return == pytest.approx(0.0, abs=1e-9)


def test_backtest_runner_with_trades():
    """Strategy that buys on bar 0 produces at least one trade."""
    traded = []

    def on_bar(bar):
        if bar.datetime == 0:
            # (symbol_id, direction_long, order_type_limit, price, volume)
            return [(0, True, False, 0.0, 10.0)]  # market buy
        return []

    def on_trade(trade_id, order_id, symbol_id, direction_long, price, volume, commission, dt):
        traded.append(price)

    cfg = make_config()
    runner = BacktestRunner(cfg, on_bar, on_trade)
    bars = [Bar(0, i * 86400, 10.0, 10.5, 9.8, 10.2, 1000.0) for i in range(5)]
    metrics = runner.run_batch(bars)
    assert len(traded) == 1
    assert metrics.total_trades == 1
    assert metrics.win_rate in (0.0, 1.0)  # one trade, one outcome
