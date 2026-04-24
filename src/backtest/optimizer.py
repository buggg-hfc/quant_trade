"""GridOptimizer: parameter grid search with multiprocessing.

Windows spawn-mode safe: _run_one is a module-level function that receives
(module_path, class_name) strings and re-imports the strategy class inside
the subprocess using importlib. Class objects are never passed across the
process boundary.
"""
from __future__ import annotations

import importlib
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import product
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    best_params: dict
    best_score: float
    all_results: list[tuple[dict, float]]
    metric: str

    def top_n(self, n: int = 5) -> list[tuple[dict, float]]:
        return sorted(self.all_results, key=lambda x: x[1], reverse=True)[:n]


def _run_one(args: tuple) -> tuple[dict, float]:
    """Worker function — executes inside a subprocess (spawn-safe)."""
    (module_path, class_name, params, symbols, start, end, interval, adjust, metric, db_path) = args

    # Re-import strategy class inside subprocess
    mod = importlib.import_module(module_path)
    strategy_cls = getattr(mod, class_name)
    strategy = strategy_cls(**params)

    from src.data.database import BarDatabase
    from src.backtest.engine import BacktestEngine
    db = BarDatabase(db_path)
    engine = BacktestEngine(db=db)

    try:
        result = engine.run(strategy, symbols, start, end, interval=interval, adjust=adjust)
        score = getattr(result.metrics, metric, 0.0)
        return params, float(score)
    except Exception as e:
        logger.warning(f"Run failed for params {params}: {e}")
        return params, float("-inf")


class GridOptimizer:
    """Exhaustive parameter grid search with parallel subprocess workers."""

    def optimize(
        self,
        strategy_cls: type,
        param_grid: dict[str, list],
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "daily",
        adjust: str = "qfq",
        metric: str = "sharpe_ratio",
        n_jobs: int = 4,
        db_path: Optional[str] = None,
    ) -> OptimizationResult:
        from src.data.database import BarDatabase

        db_path = db_path or str(BarDatabase().path)
        module_path = strategy_cls.__module__
        class_name = strategy_cls.__name__

        keys = list(param_grid.keys())
        combos = [dict(zip(keys, vals)) for vals in product(*param_grid.values())]
        logger.info(f"Grid search: {len(combos)} combinations, metric={metric}, n_jobs={n_jobs}")

        args_list = [
            (module_path, class_name, params, symbols, start, end, interval, adjust, metric, db_path)
            for params in combos
        ]

        all_results: list[tuple[dict, float]] = []
        with ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = {executor.submit(_run_one, args): args[2] for args in args_list}
            for future in as_completed(futures):
                params, score = future.result()
                all_results.append((params, score))

        all_results.sort(key=lambda x: x[1], reverse=True)
        best_params, best_score = all_results[0]
        logger.info(f"Best: {best_params}  {metric}={best_score:.4f}")
        return OptimizationResult(best_params, best_score, all_results, metric)


if __name__ == "__main__":
    # Windows spawn guard — required when using multiprocessing on Windows
    pass
