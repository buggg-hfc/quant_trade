"""CLI backtest entry point.

Usage:
    python run_backtest.py --strategy MACrossStrategy --start 2020-01-01 --end 2024-12-31
    python run_backtest.py --strategy MACrossStrategy --symbol 000001.SZ --start 2022-01-01
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest from the CLI")
    parser.add_argument("--strategy", required=True, help="Strategy class name (in strategies/)")
    parser.add_argument("--symbol", default="000001.SZ", help="Symbol(s), comma-separated")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--capital", type=float, default=1_000_000)
    parser.add_argument("--output", default="reports/backtest_result.html")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbol.split(",")]

    # Discover strategy class
    strategy_cls = None
    for module_name in [f"strategies.{args.strategy.lower()}", f"src.strategy.examples.{args.strategy.lower()}"]:
        try:
            mod = importlib.import_module(module_name)
            strategy_cls = getattr(mod, args.strategy, None)
            if strategy_cls:
                break
        except ModuleNotFoundError:
            continue

    if strategy_cls is None:
        print(f"ERROR: Strategy '{args.strategy}' not found in strategies/ or src/strategy/examples/")
        sys.exit(1)

    from src.backtest.engine import BacktestEngine
    engine = BacktestEngine(
        strategy_cls=strategy_cls,
        symbols=symbols,
        start=args.start,
        end=args.end,
        initial_capital=args.capital,
    )
    result = engine.run()
    print(result.metrics)
    result.save_report(args.output)
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
