"""CLI live trading entry point.

Usage:
    python run_live.py --gateway paper --strategy MACrossStrategy
    python run_live.py --gateway crypto --exchange binance --sandbox true --strategy CryptoGridStrategy
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start live trading from the CLI")
    parser.add_argument("--gateway", required=True, choices=["paper", "ctp", "xtp", "crypto"])
    parser.add_argument("--strategy", required=True, help="Strategy class name")
    parser.add_argument("--exchange", default="binance", help="Exchange ID (crypto gateway only)")
    parser.add_argument("--sandbox", type=lambda x: x.lower() == "true", default=True)
    parser.add_argument("--symbol", default="", help="Symbol override (comma-separated)")
    args = parser.parse_args()

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
        print(f"ERROR: Strategy '{args.strategy}' not found")
        sys.exit(1)

    from src.core.engine import MainEngine
    engine = MainEngine(gateway=args.gateway, exchange=args.exchange, sandbox=args.sandbox)
    engine.add_strategy(strategy_cls())
    print(f"Starting live trading: gateway={args.gateway}, strategy={args.strategy}")
    engine.start()


if __name__ == "__main__":
    main()
