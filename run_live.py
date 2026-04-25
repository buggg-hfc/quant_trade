"""CLI live trading entry point.

Usage:
    python run_live.py --gateway paper --strategy MACrossStrategy
    python run_live.py --gateway crypto --exchange binance --sandbox true --strategy CryptoGridStrategy
    python run_live.py --gateway ctp --strategy MACrossStrategy
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
    parser = argparse.ArgumentParser(description="Start live trading from the CLI")
    parser.add_argument("--gateway",  required=True, choices=["paper", "ctp", "xtp", "crypto"])
    parser.add_argument("--strategy", required=True, help="Strategy class name")
    parser.add_argument("--exchange", default="binance", help="Exchange ID (crypto only)")
    parser.add_argument("--sandbox",  type=lambda x: x.lower() == "true", default=True)
    parser.add_argument("--symbol",   default="", help="Symbol(s) comma-separated")
    args = parser.parse_args()

    strategy_cls = _find_strategy(args.strategy)
    if strategy_cls is None:
        print(f"ERROR: Strategy '{args.strategy}' not found in strategies/ or src/strategy/examples/")
        sys.exit(1)

    from src.core.engine import MainEngine
    engine = MainEngine(
        gateway=args.gateway,
        exchange=args.exchange,
        sandbox=args.sandbox,
    )
    engine.add_strategy(strategy_cls())
    print(f"Starting live trading: gateway={args.gateway}, strategy={args.strategy}")
    print("Press Ctrl+C to stop.")
    engine.start()


if __name__ == "__main__":
    main()
