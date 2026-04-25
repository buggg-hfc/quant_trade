"""Tests for PaperGateway order matching and state tracking."""
import pytest
from unittest.mock import patch, MagicMock
from src.core.object import BarData, AccountData, PositionData

_MOCK_SETTINGS = MagicMock()
_MOCK_SETTINGS.backtest.initial_capital = 100_000.0
_MOCK_SETTINGS.backtest.commission_rate = 0.0003
_MOCK_SETTINGS.backtest.slippage = 0.0
_MOCK_SETTINGS.backtest.price_limit_pct = 0.10

with patch("src.utils.config.get_settings", return_value=_MOCK_SETTINGS):
    from src.trading.paper_gateway import PaperGateway
    from src.trading.base_gateway import OrderRequest


def _bar(close: float, sym: str = "TEST", ts: int = 1_700_000_000) -> BarData:
    return BarData(
        symbol=sym, symbol_id=0, datetime=ts,
        open=close, high=close + 1, low=close - 1, close=close, volume=10_000,
    )


@pytest.fixture
def gw():
    with patch("src.trading.paper_gateway.get_settings", return_value=_MOCK_SETTINGS):
        g = PaperGateway(initial_capital=100_000.0)
        g.connect()
        return g


class TestPaperGatewayConnect:
    def test_connect_sets_up(self, gw):
        assert gw._cash == 100_000.0

    def test_query_account_initial(self, gw):
        acc = gw.query_account()
        assert acc.balance == pytest.approx(100_000.0)
        assert acc.total_pnl == pytest.approx(0.0)


class TestPaperGatewayOrders:
    def test_send_order_returns_id(self, gw):
        req = OrderRequest("TEST", "LONG", "LIMIT", price=10.0, volume=100.0)
        oid = gw.send_order(req)
        assert oid != ""

    def test_order_accepted_after_send(self, gw):
        req = OrderRequest("TEST", "LONG", "LIMIT", price=10.0, volume=100.0)
        oid = gw.send_order(req)
        order = gw.order_book.get(oid)
        assert order.status == "ACCEPTED"

    def test_limit_buy_fills_when_open_below_price(self, gw):
        fills = []
        gw.on_trade(fills.append)

        req = OrderRequest("TEST", "LONG", "LIMIT", price=12.0, volume=100.0)
        gw.send_order(req)
        gw.process_bar(_bar(10.0, "TEST"))   # open=10 < price=12 → fill

        assert len(fills) == 1
        assert fills[0].direction == "LONG"
        assert fills[0].volume == pytest.approx(100.0)

    def test_limit_buy_no_fill_when_open_above_price(self, gw):
        fills = []
        gw.on_trade(fills.append)

        req = OrderRequest("TEST", "LONG", "LIMIT", price=8.0, volume=100.0)
        gw.send_order(req)
        gw.process_bar(_bar(10.0, "TEST"))   # open=10 > price=8 → no fill

        assert len(fills) == 0

    def test_limit_sell_fills_when_open_above_price(self, gw):
        fills = []
        gw.on_trade(fills.append)

        req = OrderRequest("TEST", "SHORT", "LIMIT", price=9.0, volume=50.0)
        gw.send_order(req)
        gw.process_bar(_bar(10.0, "TEST"))   # open=10 >= price=9 → fill

        assert len(fills) == 1
        assert fills[0].direction == "SHORT"

    def test_cancel_order(self, gw):
        req = OrderRequest("TEST", "LONG", "LIMIT", price=12.0, volume=100.0)
        oid = gw.send_order(req)
        gw.cancel_order(oid)
        assert gw.order_book.get(oid).status == "CANCELLED"
        assert gw.order_book.get(oid) not in gw.order_book.open_orders()


class TestPaperGatewayPnL:
    def test_buy_reduces_cash(self, gw):
        req = OrderRequest("TEST", "LONG", "LIMIT", price=12.0, volume=100.0)
        gw.send_order(req)
        gw.process_bar(_bar(10.0))   # fills at open=10
        # cash spent: 10 * 100 + commission = 1 000 + 0.3 = 1 000.3
        assert gw._cash < 100_000.0

    def test_round_trip_pnl(self, gw):
        fills = []
        gw.on_trade(fills.append)

        # Buy 100 at open=10
        req = OrderRequest("TEST", "LONG", "LIMIT", price=12.0, volume=100.0)
        gw.send_order(req)
        gw.process_bar(_bar(10.0))

        # Sell 100 at open=20
        req2 = OrderRequest("TEST", "SHORT", "LIMIT", price=18.0, volume=100.0)
        gw.send_order(req2)
        gw.process_bar(_bar(20.0))

        acc = gw.query_account()
        assert acc.total_pnl > 0   # profitable round trip

    def test_price_limit_up_rejects_buy(self, gw):
        orders = []
        gw.on_order(orders.append)

        req = OrderRequest("TEST", "LONG", "LIMIT", price=11.0, volume=100.0)
        oid = gw.send_order(req)
        # close = 10, limit_up = 11 → buy at limit-up is rejected
        gw.process_bar(_bar(10.0))   # close=10, limit_up=11
        # Make close hit the limit
        bar = BarData(symbol="TEST", symbol_id=0, datetime=0,
                     open=11.0, high=11.0, low=11.0, close=11.0, volume=1000)
        gw.send_order(OrderRequest("TEST", "LONG", "LIMIT", price=12.0, volume=50.0))
        gw.process_bar(bar)  # close=11 = limit_up → long rejected

        # At limit-up the pending buy is cancelled (ACCEPTED→CANCELLED is valid)
        cancelled = [o for o in orders if o.status == "CANCELLED"]
        assert len(cancelled) >= 1


class TestOrderBook:
    def test_invalid_transition_ignored(self, gw):
        from src.trading.base_gateway import OrderBook
        from src.core.object import OrderData
        ob = OrderBook()
        order = OrderData(order_id="x", symbol="T", direction="LONG",
                         order_type="LIMIT", price=10.0, volume=1.0, status="FILLED")
        ob.add(order)
        result = ob.transition("x", "ACCEPTED")  # FILLED → ACCEPTED is invalid
        assert not result
        assert ob.get("x").status == "FILLED"

    def test_open_orders_excludes_terminal(self, gw):
        from src.trading.base_gateway import OrderBook
        from src.core.object import OrderData
        ob = OrderBook()
        o = OrderData(order_id="y", symbol="T", direction="LONG",
                     order_type="LIMIT", price=10.0, volume=1.0, status="SUBMITTED")
        ob.add(o)
        ob.transition("y", "ACCEPTED")
        ob.transition("y", "FILLED", 1.0)
        assert len(ob.open_orders()) == 0
