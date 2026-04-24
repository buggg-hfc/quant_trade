"""Plotly HTML report generator for backtest results."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.backtest.engine import BacktestResult


def generate_report(
    result: BacktestResult,
    strategy_name: str = "Strategy",
    output_path: Optional[str] = None,
) -> str:
    """Generate an HTML report. Returns the file path."""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"reports/backtest_{strategy_name}_{ts}.html"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=("Equity Curve", "Drawdown", "Trade P&L"),
        row_heights=[0.5, 0.25, 0.25],
        shared_xaxes=True,
        vertical_spacing=0.06,
    )

    # Equity curve
    eq = result.equity_curve
    fig.add_trace(
        go.Scatter(x=eq.index, y=eq.values, name="Equity", line=dict(color="#2196F3")),
        row=1, col=1,
    )

    # Drawdown
    rolling_max = eq.cummax()
    drawdown = (eq - rolling_max) / rolling_max
    fig.add_trace(
        go.Scatter(
            x=drawdown.index, y=drawdown.values,
            name="Drawdown", fill="tozeroy",
            line=dict(color="#F44336"), fillcolor="rgba(244,67,54,0.2)",
        ),
        row=2, col=1,
    )

    # Trade scatter
    if result.trades:
        trades_df = pd.DataFrame(result.trades)
        wins = trades_df[trades_df.get("pnl", 0) >= 0] if "pnl" in trades_df else pd.DataFrame()
        fig.add_trace(
            go.Scatter(
                x=pd.to_datetime(trades_df["datetime"], unit="s"),
                y=trades_df["price"],
                mode="markers",
                name="Trades",
                marker=dict(color="#4CAF50", size=6, symbol="circle"),
            ),
            row=3, col=1,
        )

    m = result.metrics
    title = (
        f"{strategy_name} | "
        f"Return={m.total_return:.2%}  Sharpe={m.sharpe_ratio:.2f}  "
        f"MaxDD={m.max_drawdown:.2%}  Trades={m.total_trades}  "
        f"WinRate={m.win_rate:.2%}"
    )
    fig.update_layout(
        title=title,
        height=750,
        template="plotly_dark",
        showlegend=True,
        margin=dict(l=50, r=20, t=80, b=40),
    )

    fig.write_html(output_path, include_plotlyjs="cdn")
    return output_path
