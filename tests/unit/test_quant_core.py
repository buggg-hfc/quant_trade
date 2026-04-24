"""Unit tests for the quant_core Rust extension (Phase 1)."""
import pytest
from quant_core import Bar, BrokerConfigPy, BacktestRunner, BacktestMetrics, EventEngine, Position


# ─── Helpers ─────────────────────────────────────────────────────────────────

def cfg(**kw) -> BrokerConfigPy:
    defaults = dict(
        commission_rate=0.0,        # zero commission makes P&L arithmetic exact
        slippage=0.0,
        price_limit_pct=0.10,
        initial_capital=100_000.0,
        max_position_pct=0.9,
        daily_loss_limit=0.50,
        max_order_volume=100_000.0,
        max_fill_volume_per_bar=0.0,
    )
    defaults.update(kw)
    return BrokerConfigPy(**defaults)


def make_bars(n: int, base_price: float = 10.0, symbol_id: int = 0) -> list[Bar]:
    return [Bar(symbol_id, i * 86400, base_price, base_price * 1.01,
                base_price * 0.99, base_price, 10_000.0)
            for i in range(n)]


# ─── Bar ─────────────────────────────────────────────────────────────────────

class TestBar:
    def test_fields(self):
        b = Bar(1, 1000, 10.0, 11.0, 9.5, 10.5, 500.0)
        assert b.symbol_id == 1
        assert b.datetime == 1000
        assert b.open == 10.0
        assert b.high == 11.0
        assert b.low == 9.5
        assert b.close == 10.5
        assert b.volume == 500.0

    def test_repr(self):
        b = Bar(0, 0, 1.0, 1.0, 1.0, 1.0, 0.0)
        assert "Bar" in repr(b)


# ─── EventEngine ─────────────────────────────────────────────────────────────

class TestEventEngine:
    def test_start_stop(self):
        e = EventEngine()
        e.start()
        e.stop()

    def test_put_bar(self):
        e = EventEngine()
        e.start()
        b = Bar(0, 0, 1.0, 1.0, 1.0, 1.0, 0.0)
        e.put_bar(b)  # should not raise
        e.stop()


# ─── BacktestRunner — no trades ──────────────────────────────────────────────

class TestBacktestNoTrades:
    def test_zero_trades(self):
        bar_count = []
        def on_bar(bar): bar_count.append(bar.symbol_id); return []
        def on_trade(*a): pass

        r = BacktestRunner(cfg(), on_bar, on_trade)
        m = r.run_batch(make_bars(10))
        assert len(bar_count) == 10
        assert m.total_trades == 0
        assert m.total_return == pytest.approx(0.0, abs=1e-9)

    def test_equity_unchanged_when_no_position(self):
        def on_bar(bar): return []
        def on_trade(*a): pass
        r = BacktestRunner(cfg(), on_bar, on_trade)
        r.run_batch(make_bars(5))
        assert r.current_equity() == pytest.approx(100_000.0, rel=1e-9)


# ─── BacktestRunner — single buy, hold, check M2M ───────────────────────────

class TestBacktestMTM:
    def test_buy_and_hold_pnl(self):
        """Buy 100 shares at bar-0 open=10; price rises to 12 by bar-4 → expected M2M gain."""
        prices = [10.0, 10.5, 11.0, 11.5, 12.0]
        bought = []
        trades = []

        def on_bar(bar):
            if bar.datetime == 0 and not bought:
                bought.append(True)
                return [(0, True, False, 0.0, 100.0)]  # market buy 100
            return []

        def on_trade(tid, oid, sym, is_long, price, vol, commission, dt):
            trades.append(price)

        r = BacktestRunner(cfg(), on_bar, on_trade)
        bars = [Bar(0, i, p, p * 1.01, p * 0.99, p, 10_000.0)
                for i, p in enumerate(prices)]
        m = r.run_batch(bars)

        assert len(trades) == 1
        assert trades[0] == pytest.approx(10.0, rel=1e-9)  # slippage=0
        # Final equity: 100_000 + 100*(12-10) = 100_200 (no commission)
        assert r.current_equity() == pytest.approx(100_200.0, rel=1e-3)

    def test_buy_sell_round_trip(self):
        """Buy 100 @ 10, sell 100 @ 12 → realized P&L = +200."""
        state = {"bought": False}

        def on_bar(bar):
            if bar.datetime == 0 and not state["bought"]:
                state["bought"] = True
                return [(0, True, False, 0.0, 100.0)]
            if bar.datetime == 2:
                return [(0, False, False, 0.0, 100.0)]  # market sell
            return []

        def on_trade(*a): pass

        r = BacktestRunner(cfg(), on_bar, on_trade)
        bars = [Bar(0, 0, 10.0, 10.1, 9.9, 10.0, 9999.0),
                Bar(0, 1, 11.0, 11.1, 10.9, 11.0, 9999.0),
                Bar(0, 2, 12.0, 12.1, 11.9, 12.0, 9999.0)]
        m = r.run_batch(bars)
        assert m.total_trades == 2
        assert r.current_equity() == pytest.approx(100_200.0, rel=1e-3)

    def test_position_reported(self):
        state = {"done": False}

        def on_bar(bar):
            if not state["done"]:
                state["done"] = True
                return [(0, True, False, 0.0, 50.0)]
            return []

        def on_trade(*a): pass

        r = BacktestRunner(cfg(), on_bar, on_trade)
        r.run_batch(make_bars(3))
        positions = r.get_positions()
        assert len(positions) == 1
        sym_id, net_vol, avg_px, upnl, rpnl = positions[0]
        assert sym_id == 0
        assert net_vol == pytest.approx(50.0, rel=1e-9)


# ─── BacktestRunner — risk rejection ─────────────────────────────────────────

class TestRiskRejection:
    def test_volume_too_large_skipped(self):
        trades = []

        def on_bar(bar):
            return [(0, True, False, 0.0, 999_999.0)]  # exceeds max_order_volume

        def on_trade(*a): trades.append(1)

        c = cfg(max_order_volume=1000.0)
        r = BacktestRunner(c, on_bar, on_trade)
        r.run_batch(make_bars(3))
        assert len(trades) == 0

    def test_normal_order_fills(self):
        trades = []
        done = [False]

        def on_bar(bar):
            if not done[0]:
                done[0] = True
                return [(0, True, False, 0.0, 100.0)]
            return []

        def on_trade(*a): trades.append(1)

        r = BacktestRunner(cfg(), on_bar, on_trade)
        r.run_batch(make_bars(5))
        assert len(trades) == 1


# ─── BacktestRunner — metrics quality ────────────────────────────────────────

class TestMetrics:
    def test_metrics_fields_present(self):
        def on_bar(bar): return []
        def on_trade(*a): pass
        m = BacktestRunner(cfg(), on_bar, on_trade).run_batch(make_bars(5))
        assert hasattr(m, "sharpe")
        assert hasattr(m, "sortino")
        assert hasattr(m, "max_drawdown")
        assert hasattr(m, "calmar")
        assert hasattr(m, "win_rate")
        assert hasattr(m, "profit_factor")
        assert hasattr(m, "total_trades")
        assert hasattr(m, "initial_capital")
        assert hasattr(m, "final_equity")

    def test_win_rate_profitable_close(self):
        """Buy low, sell high → closing trade is a win.
        win_rate counts ALL trades: buy (realized=0, neutral) + sell (realized>0, win).
        With 2 trades and 1 win → win_rate = 0.5.
        Also checks total_return > 0 and equity grew.
        """
        done = [False]

        def on_bar(bar):
            if not done[0]:
                done[0] = True
                return [(0, True, False, 0.0, 10.0)]
            if bar.datetime == 4:
                return [(0, False, False, 0.0, 10.0)]
            return []

        def on_trade(*a): pass

        bars = [Bar(0, i, 10.0 + i, 11.0 + i, 9.0 + i, 10.0 + i, 9999.0)
                for i in range(6)]
        m = BacktestRunner(cfg(), on_bar, on_trade).run_batch(bars)
        assert m.total_trades == 2
        # Buy: realized=0 (not a win); Sell: realized>0 (win) → win_rate = 0.5
        assert m.win_rate == pytest.approx(0.5, abs=0.01)
        assert m.total_return > 0.0, f"Expected positive return, got {m.total_return}"


# ─── BacktestRunner — multi-symbol ───────────────────────────────────────────

class TestMultiSymbol:
    def test_two_symbols_independent(self):
        """Interleaved bars for sym0 and sym1; buy both, verify separate positions."""
        bought = set()
        trade_count = [0]

        def on_bar(bar):
            if bar.symbol_id not in bought:
                bought.add(bar.symbol_id)
                return [(bar.symbol_id, True, False, 0.0, 10.0)]
            return []

        def on_trade(*a): trade_count[0] += 1

        # Interleaved: dt=0 sym0, dt=0 sym1, dt=1 sym0, dt=1 sym1 ...
        bars = []
        for dt in range(5):
            for sid in range(2):
                bars.append(Bar(sid, dt, 10.0, 10.5, 9.5, 10.0, 5000.0))

        r = BacktestRunner(cfg(), on_bar, on_trade)
        r.run_batch(bars)
        assert trade_count[0] == 2
        positions = r.get_positions()
        assert len(positions) == 2


# ─── BrokerConfigPy defaults ─────────────────────────────────────────────────

class TestBrokerConfigDefaults:
    def test_default_construction(self):
        c = BrokerConfigPy()
        assert c.commission_rate == pytest.approx(0.0003, rel=1e-9)
        assert c.slippage == pytest.approx(0.001, rel=1e-9)
        assert c.initial_capital == pytest.approx(1_000_000.0, rel=1e-9)
