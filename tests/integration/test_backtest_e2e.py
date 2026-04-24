"""End-to-end backtest integration test using a simple MA-cross strategy stub."""
import pytest
from quant_core import Bar, BrokerConfigPy, BacktestRunner


class SimpleMACrossStrategy:
    """
    Minimal MA-cross for testing. Uses a fixed window=3.
    Buys when close > simple_ma(3), sells when close < simple_ma(3).
    Operates on symbol_id=0 only.
    """
    WINDOW = 3
    VOLUME = 100.0

    def __init__(self):
        self.closes: list[float] = []
        self.position: float = 0.0  # +100 = long, 0 = flat

    def on_bar(self, bar: Bar) -> list:
        if bar.symbol_id != 0:
            return []
        self.closes.append(bar.close)
        if len(self.closes) < self.WINDOW:
            return []
        ma = sum(self.closes[-self.WINDOW:]) / self.WINDOW
        orders = []
        if bar.close > ma and self.position == 0.0:
            orders.append((0, True, False, 0.0, self.VOLUME))   # market buy
        elif bar.close < ma and self.position > 0.0:
            orders.append((0, False, False, 0.0, self.VOLUME))  # market sell
        return orders

    def on_trade(self, tid, oid, sym, is_long, price, vol, commission, dt):
        self.position += vol if is_long else -vol


def make_trending_bars(n: int = 50) -> list[Bar]:
    """Upward trend with small noise — MA-cross should produce profitable trades."""
    import math
    bars = []
    for i in range(n):
        trend = 10.0 + i * 0.05
        noise = 0.02 * math.sin(i * 0.8)
        c = trend + noise
        bars.append(Bar(0, i * 86400, c * 0.998, c * 1.01, c * 0.99, c, 5000.0))
    return bars


@pytest.fixture
def cfg():
    return BrokerConfigPy(
        commission_rate=0.0003,
        slippage=0.001,
        price_limit_pct=0.10,
        initial_capital=100_000.0,
        max_position_pct=0.5,
        daily_loss_limit=0.20,
        max_order_volume=10_000.0,
    )


class TestMACrossE2E:
    def test_runs_without_error(self, cfg):
        strat = SimpleMACrossStrategy()
        r = BacktestRunner(cfg, strat.on_bar, strat.on_trade)
        m = r.run_batch(make_trending_bars(50))
        assert m is not None

    def test_produces_trades(self, cfg):
        strat = SimpleMACrossStrategy()
        r = BacktestRunner(cfg, strat.on_bar, strat.on_trade)
        m = r.run_batch(make_trending_bars(50))
        assert m.total_trades >= 1

    def test_trending_market_positive_return(self, cfg):
        strat = SimpleMACrossStrategy()
        r = BacktestRunner(cfg, strat.on_bar, strat.on_trade)
        m = r.run_batch(make_trending_bars(100))
        # Upward trend → MA-cross should produce positive return
        assert m.total_return > 0.0, f"Expected positive return, got {m.total_return:.4f}"

    def test_metrics_sane(self, cfg):
        strat = SimpleMACrossStrategy()
        r = BacktestRunner(cfg, strat.on_bar, strat.on_trade)
        m = r.run_batch(make_trending_bars(100))
        assert 0.0 <= m.win_rate <= 1.0
        assert m.max_drawdown <= 0.0
        assert m.initial_capital == pytest.approx(100_000.0)
        assert m.final_equity > 0.0

    def test_reproduced_deterministically(self, cfg):
        """Same bars + strategy must produce identical metrics."""
        bars = make_trending_bars(60)

        strat1 = SimpleMACrossStrategy()
        r1 = BacktestRunner(cfg, strat1.on_bar, strat1.on_trade)
        m1 = r1.run_batch(bars)

        strat2 = SimpleMACrossStrategy()
        r2 = BacktestRunner(cfg, strat2.on_bar, strat2.on_trade)
        m2 = r2.run_batch(bars)

        assert m1.total_return == pytest.approx(m2.total_return, rel=1e-9)
        assert m1.total_trades == m2.total_trades
        assert m1.sharpe == pytest.approx(m2.sharpe, rel=1e-9)
