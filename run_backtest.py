"""CLI backtest entry point.

Usage:
    python run_backtest.py --strategy MACrossStrategy
    python run_backtest.py --strategy MACrossStrategy --symbol 000001.SZ --start 2022-01-01 --end 2024-12-31
    python run_backtest.py --strategy MomentumRotationStrategy --symbol 000001.SZ,600036.SH
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _find_strategy(name: str):
    for module_path in [f"strategies.{name.lower()}", f"src.strategy.examples.{name.lower()}"]:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, name, None)
            if cls is not None:
                return cls
        except ModuleNotFoundError:
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest from the CLI")
    parser.add_argument("--strategy", required=True, help="Strategy class name")
    parser.add_argument("--symbol",   default="000001.SZ", help="Symbol(s), comma-separated")
    parser.add_argument("--start",    default="2020-01-01")
    parser.add_argument("--end",      default="2024-12-31")
    parser.add_argument("--interval", default="daily", choices=["daily", "weekly", "monthly"])
    parser.add_argument("--adjust",   default="qfq",   choices=["qfq", "hfq", ""])
    parser.add_argument("--output",   default="")
    args = parser.parse_args()

    strategy_cls = _find_strategy(args.strategy)
    if strategy_cls is None:
        print(f"ERROR: Strategy '{args.strategy}' not found in strategies/ or src/strategy/examples/")
        sys.exit(1)

    symbols = [s.strip() for s in args.symbol.split(",")]

    from src.backtest.engine import BacktestEngine
    from src.backtest.report import generate_report

    engine = BacktestEngine()
    result = engine.run(
        strategy=strategy_cls(),
        symbols=symbols,
        start=args.start,
        end=args.end,
        interval=args.interval,
        adjust=args.adjust,
    )
    print(result.summary())

    output = args.output or f"reports/backtest_{args.strategy}_{args.start[:4]}.html"
    path = generate_report(result, strategy_name=args.strategy, output_path=output)
    print(f"Report: {path}")


if __name__ == "__main__":
    main()
