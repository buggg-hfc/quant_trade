"""Python RiskManager: business-rule validation layer.

Sits upstream of every gateway.send_order() call. Chains with the Rust
RiskManager (which handles fast low-level checks: position size, daily P&L)
via a two-pass architecture:

    OrderRequest
        → Python RiskManager (blacklist, regulatory, correlation)
        → Rust RiskManager   (position cap, daily loss, max volume)
        → Gateway.send_order()

This module handles the Python pass only. It is stateless with respect to
market data — rules receive the current AccountData and positions snapshot
injected by the calling engine or gateway.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.object import OrderData, AccountData, PositionData
from src.risk.rules import (
    RuleFn,
    blacklist_rule,
    max_position_rule,
    daily_loss_rule,
    max_order_volume_rule,
)
from src.utils.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.approved


class RiskManager:
    """Composable rule chain for pre-order validation."""

    def __init__(
        self,
        blacklist: set[str] | None = None,
        extra_rules: list[RuleFn] | None = None,
    ) -> None:
        cfg = get_settings().risk
        self._rules: list[RuleFn] = [
            blacklist_rule(blacklist or set()),
            max_position_rule(cfg.max_position_pct),
            daily_loss_rule(cfg.daily_loss_limit),
            max_order_volume_rule(cfg.max_order_volume),
        ]
        if extra_rules:
            self._rules.extend(extra_rules)

    def check(
        self,
        order: OrderData,
        account: AccountData,
        positions: dict[str, PositionData],
    ) -> RiskCheckResult:
        for rule in self._rules:
            ok, reason = rule(order, account, positions)
            if not ok:
                logger.warning(f"Risk rejected order {order.order_id} ({order.symbol}): {reason}")
                return RiskCheckResult(approved=False, reason=reason)
        return RiskCheckResult(approved=True)

    def add_rule(self, rule: RuleFn) -> None:
        self._rules.append(rule)

    def set_blacklist(self, symbols: set[str]) -> None:
        """Replace the blacklist rule (first rule by convention)."""
        self._rules[0] = blacklist_rule(symbols)
