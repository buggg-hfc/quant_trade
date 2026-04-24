"""BacktestEngine: multi-symbol Rust-accelerated backtest.

Workflow:
1. Load OHLCV bars from SQLite for each symbol.
2. Assign symbol_id via SymbolRegistry; time-align across symbols.
3. Build a numpy structured array and pass it to Rust BacktestRunner.run_batch().
4. Collect BacktestMetrics and wrap them in a BacktestResult.

The Rust engine handles matching/risk/P&L; Python strategy on_bar/on_trade
are invoked as callbacks (GIL held for the entire batch loop).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

from src.core.object import SymbolRegistry, BarData, TradeData, PositionData, AccountData
from src.data.database import BarDatabase
from src.utils.config import get_settings

if TYPE_CHECKING:
    from src.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    metrics: object          # quant_core.BacktestMetrics
    equity_curve: pd.Series  # date → equity
    trades: list[dict]
    symbol_registry: dict[int, str] = field(default_factory=dict)

    @property
    def sharpe(self) -> float:
        return self.metrics.sharpe_ratio

    @property
    def max_drawdown(self) -> float:
        return self.metrics.max_drawdown

    @property
    def total_return(self) -> float:
        return self.metrics.total_return

    def summary(self) -> str:
        m = self.metrics
        return (
            f"Return={m.total_return:.2%}  Sharpe={m.sharpe_ratio:.2f}  "
            f"MaxDD={m.max_drawdown:.2%}  Trades={m.total_trades}  "
            f"WinRate={m.win_rate:.2%}"
        )


class BacktestEngine:
    """Run a single strategy against one or more symbols."""

    def __init__(self, db: Optional[BarDatabase] = None) -> None:
        self._db = db or BarDatabase()

    def run(
        self,
        strategy: "BaseStrategy",
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "daily",
        adjust: str = "qfq",
    ) -> BacktestResult:
        try:
            from quant_core import BacktestRunner, BrokerConfigPy
        except ImportError:
            raise ImportError("quant_core not built. Run: maturin develop --release")

        cfg = get_settings()
        broker_cfg = BrokerConfigPy(
            commission_rate=cfg.backtest.commission_rate,
            slippage=cfg.backtest.slippage,
            price_limit_pct=cfg.backtest.price_limit_pct,
        )

        bars_np, dates, id_to_sym = self._load_bars(symbols, start, end, interval, adjust)
        if len(bars_np) == 0:
            raise ValueError(f"No bars loaded for {symbols} [{start}→{end}]")

        strategy._positions = {}
        strategy._account = AccountData(
            balance=cfg.backtest.initial_capital,
            available=cfg.backtest.initial_capital,
        )
        strategy.on_init()

        collected_trades: list[dict] = []

        def _on_bar(bar_obj) -> list:
            sym = id_to_sym[bar_obj.symbol_id]
            bar = BarData(
                symbol=sym,
                symbol_id=bar_obj.symbol_id,
                datetime=bar_obj.datetime,
                open=bar_obj.open,
                high=bar_obj.high,
                low=bar_obj.low,
                close=bar_obj.close,
                volume=bar_obj.volume,
            )
            strategy.on_bar(bar)
            raw_orders = strategy._pop_orders()
            # Convert to Rust-compatible tuples: (symbol_id, direction, price, volume)
            rust_orders = []
            for o in raw_orders:
                sid = SymbolRegistry.get_or_register(o["symbol"])
                rust_orders.append((sid, o["direction"], o["price"], o["volume"]))
            return rust_orders

        def _on_trade(trade_obj) -> None:
            sym = id_to_sym[trade_obj.symbol_id]
            trade = TradeData(
                trade_id=str(trade_obj.trade_id),
                order_id="",
                symbol=sym,
                direction=trade_obj.direction,
                price=trade_obj.price,
                volume=trade_obj.volume,
                commission=trade_obj.commission,
                datetime=trade_obj.datetime,
            )
            # Update strategy positions view
            pos = strategy._positions.setdefault(sym, PositionData(symbol=sym))
            if trade.direction == "LONG":
                total = pos.avg_price * pos.net_volume + trade.price * trade.volume
                pos.net_volume += trade.volume
                pos.avg_price = total / pos.net_volume if pos.net_volume else 0.0
            else:
                pos.net_volume -= trade.volume
                if abs(pos.net_volume) < 1e-9:
                    pos.avg_price = 0.0

            strategy.on_trade(trade)
            collected_trades.append({
                "symbol": sym,
                "direction": trade.direction,
                "price": trade.price,
                "volume": trade.volume,
                "commission": trade.commission,
                "datetime": trade.datetime,
            })

        runner = BacktestRunner(
            initial_capital=cfg.backtest.initial_capital,
            broker_config=broker_cfg,
            on_bar=_on_bar,
            on_trade=_on_trade,
        )

        metrics = runner.run_batch(bars_np)
        strategy.on_stop()

        equity_values = np.array(metrics.equity_curve)
        equity_series = pd.Series(
            equity_values,
            index=pd.date_range(start=start, periods=len(equity_values), freq="B"),
            name="equity",
        )

        return BacktestResult(
            metrics=metrics,
            equity_curve=equity_series,
            trades=collected_trades,
            symbol_registry=dict(id_to_sym),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_bars(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str,
        adjust: str,
    ):
        SymbolRegistry.reset()
        frames = []
        id_to_sym: dict[int, str] = {}

        for sym in symbols:
            df = self._db.load(sym, interval, start, end, adjust=adjust)
            if df.empty:
                logger.warning(f"No cached data for {sym}; skipping")
                continue
            sid = SymbolRegistry.get_or_register(sym)
            id_to_sym[sid] = sym
            df = df.copy()
            df["symbol_id"] = np.uint32(sid)
            df["datetime"] = df.index.astype(np.int64) // 10**9  # ns → s
            frames.append(df)

        if not frames:
            return np.array([]), [], id_to_sym

        merged = pd.concat(frames).sort_values("datetime")
        dates = merged.index.tolist()

        # Build numpy structured array matching Rust Bar layout
        arr = np.zeros(len(merged), dtype=[
            ("symbol_id", np.uint32),
            ("datetime", np.int64),
            ("open",      np.float64),
            ("high",      np.float64),
            ("low",       np.float64),
            ("close",     np.float64),
            ("volume",    np.float64),
        ])
        arr["symbol_id"] = merged["symbol_id"].values
        arr["datetime"]  = merged["datetime"].values
        arr["open"]      = merged["open"].values
        arr["high"]      = merged["high"].values
        arr["low"]       = merged["low"].values
        arr["close"]     = merged["close"].values
        arr["volume"]    = merged["volume"].values

        return arr, dates, id_to_sym
