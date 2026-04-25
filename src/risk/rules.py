"""Individual risk rule implementations.

Each rule is a callable that returns (approved: bool, reason: str).
Rules are composed by RiskManager and evaluated in order; the first
rejection short-circuits the chain.
"""
from __future__ import annotations

from typing import Callable

from src.core.object import OrderData, AccountData, PositionData

RuleResult = tuple[bool, str]
RuleFn = Callable[[OrderData, AccountData, dict[str, PositionData]], RuleResult]


def blacklist_rule(blacklist: set[str]) -> RuleFn:
    """Reject orders for blacklisted symbols."""
    def _check(order: OrderData, account: AccountData, positions: dict) -> RuleResult:
        if order.symbol in blacklist:
            return False, f"{order.symbol} is blacklisted"
        return True, ""
    return _check


def max_position_rule(max_pct: float) -> RuleFn:
    """Reject if adding this order would exceed max_pct of account balance."""
    def _check(order: OrderData, account: AccountData, positions: dict) -> RuleResult:
        if account.balance <= 0:
            return True, ""
        order_value = order.price * order.volume
        max_value = account.balance * max_pct
        current_pos = positions.get(order.symbol)
        current_value = (current_pos.net_volume * order.price) if current_pos else 0.0
        if order.direction == "LONG" and (current_value + order_value) > max_value:
            return False, (
                f"Position would exceed {max_pct:.0%} limit: "
                f"order_value={order_value:.0f}, current={current_value:.0f}, max={max_value:.0f}"
            )
        return True, ""
    return _check


def daily_loss_rule(loss_limit_pct: float) -> RuleFn:
    """Halt trading if today's realized loss exceeds limit_pct of initial balance."""
    def _check(order: OrderData, account: AccountData, positions: dict) -> RuleResult:
        if account.balance <= 0:
            return True, ""
        # total_pnl is cumulative; we use it as a proxy for intraday loss
        if account.total_pnl < -account.balance * loss_limit_pct:
            return False, (
                f"Daily loss limit reached: pnl={account.total_pnl:.0f}, "
                f"limit={-account.balance * loss_limit_pct:.0f}"
            )
        return True, ""
    return _check


def max_order_volume_rule(max_volume: float) -> RuleFn:
    """Reject single orders larger than max_volume lots."""
    def _check(order: OrderData, account: AccountData, positions: dict) -> RuleResult:
        if order.volume > max_volume:
            return False, f"Order volume {order.volume} exceeds max {max_volume}"
        return True, ""
    return _check
