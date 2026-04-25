"""Tests for RiskManager and individual rules."""
import pytest
from unittest.mock import patch, MagicMock
from src.core.object import OrderData, AccountData, PositionData

_MOCK_SETTINGS = MagicMock()
_MOCK_SETTINGS.risk.max_position_pct = 0.20
_MOCK_SETTINGS.risk.daily_loss_limit = 0.02
_MOCK_SETTINGS.risk.max_order_volume = 1000.0

with patch("src.utils.config.get_settings", return_value=_MOCK_SETTINGS):
    from src.risk.manager import RiskManager
    from src.risk.rules import (
        blacklist_rule, max_position_rule, daily_loss_rule, max_order_volume_rule,
    )


def _order(symbol="000001.SZ", direction="LONG", price=10.0, volume=100.0) -> OrderData:
    return OrderData(
        order_id="test-01", symbol=symbol, direction=direction,
        order_type="LIMIT", price=price, volume=volume,
    )

def _account(balance=100_000.0, pnl=0.0) -> AccountData:
    return AccountData(balance=balance, available=balance, total_pnl=pnl)


class TestBlacklistRule:
    def test_blacklisted_rejected(self):
        rule = blacklist_rule({"ST_BAD.SZ"})
        ok, reason = rule(_order("ST_BAD.SZ"), _account(), {})
        assert not ok
        assert "blacklisted" in reason

    def test_normal_symbol_approved(self):
        rule = blacklist_rule({"ST_BAD.SZ"})
        ok, _ = rule(_order("000001.SZ"), _account(), {})
        assert ok


class TestMaxPositionRule:
    def test_within_limit_approved(self):
        rule = max_position_rule(0.20)
        # 100 shares × 10.0 = 1 000; 20% of 100 000 = 20 000 → ok
        ok, _ = rule(_order(price=10.0, volume=100.0), _account(100_000.0), {})
        assert ok

    def test_exceeds_limit_rejected(self):
        rule = max_position_rule(0.20)
        # 5 000 shares × 10.0 = 50 000; limit = 20 000 → reject
        ok, reason = rule(_order(price=10.0, volume=5_000.0), _account(100_000.0), {})
        assert not ok
        assert "limit" in reason.lower()

    def test_zero_balance_skipped(self):
        rule = max_position_rule(0.20)
        ok, _ = rule(_order(), _account(0.0), {})
        assert ok


class TestDailyLossRule:
    def test_within_limit_approved(self):
        rule = daily_loss_rule(0.02)
        ok, _ = rule(_order(), _account(100_000.0, pnl=-1_000.0), {})
        assert ok   # -1 000 < -2 000 limit

    def test_exceeded_rejected(self):
        rule = daily_loss_rule(0.02)
        ok, reason = rule(_order(), _account(100_000.0, pnl=-3_000.0), {})
        assert not ok
        assert "loss" in reason.lower()


class TestMaxVolumeRule:
    def test_within_limit(self):
        rule = max_order_volume_rule(1000.0)
        ok, _ = rule(_order(volume=999.0), _account(), {})
        assert ok

    def test_exceeds_limit(self):
        rule = max_order_volume_rule(1000.0)
        ok, reason = rule(_order(volume=1001.0), _account(), {})
        assert not ok
        assert "volume" in reason.lower()


class TestRiskManager:
    @pytest.fixture
    def rm(self):
        with patch("src.risk.manager.get_settings", return_value=_MOCK_SETTINGS):
            return RiskManager()

    def test_clean_order_approved(self, rm):
        result = rm.check(_order(), _account(), {})
        assert result.approved
        assert bool(result)

    def test_blacklisted_rejected(self, rm):
        rm.set_blacklist({"000001.SZ"})
        result = rm.check(_order("000001.SZ"), _account(), {})
        assert not result.approved

    def test_oversized_order_rejected(self, rm):
        result = rm.check(_order(volume=2_000.0), _account(100_000.0), {})
        assert not result.approved

    def test_daily_loss_halt(self, rm):
        result = rm.check(_order(), _account(100_000.0, pnl=-5_000.0), {})
        assert not result.approved

    def test_add_custom_rule(self, rm):
        def always_reject(order, account, positions):
            return False, "custom veto"
        rm.add_rule(always_reject)
        result = rm.check(_order(), _account(), {})
        assert not result.approved
        assert "custom veto" in result.reason
