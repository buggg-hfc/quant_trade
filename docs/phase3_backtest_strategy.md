# Phase 3 — Backtest Engine & Strategy Framework

## Overview

Phase 3 delivers the end-to-end backtest pipeline: a strategy base class, technical indicators, a Rust-accelerated multi-symbol backtest engine, a grid parameter optimizer, and three example strategies.

## Directory Layout

```
src/strategy/
├── base.py             ← BaseStrategy ABC
├── indicators.py       ← SMA/EMA/RSI/MACD/ATR/Bollinger/OBV/VWAP
└── examples/
    ├── ma_cross.py     ← Dual MA crossover (A-share single symbol)
    ├── momentum_rotation.py  ← Multi-symbol momentum rotation
    └── crypto_grid.py  ← Grid trading (crypto sideways markets)

src/backtest/
├── engine.py           ← BacktestEngine (multi-symbol, Rust-backed)
├── optimizer.py        ← GridOptimizer (spawn-safe multiprocessing)
└── report.py           ← Plotly HTML report generator

strategies/             ← User-editable strategy files (hot-loaded by GUI)
├── _template.py        ← Copy this to write a new strategy
├── ma_cross.py
└── crypto_grid.py
```

## Writing a Strategy

Copy `strategies/_template.py`, rename the class, implement `on_bar`:

```python
from src.strategy.base import BaseStrategy
from src.core.object import BarData

class MyStrategy(BaseStrategy):
    # Class-level int/float → GUI-editable parameters
    fast_period: int = 5
    slow_period: int = 20
    trade_volume: float = 100.0

    def on_init(self) -> None:
        """Pre-compute indicators or set up state before first bar."""
        from collections import deque
        self._buf: deque[float] = deque(maxlen=self.slow_period)

    def on_bar(self, bar: BarData) -> None:
        self._buf.append(bar.close)
        if len(self._buf) < self.slow_period:
            return
        # Emit orders:
        if self.get_pos(bar.symbol) == 0:
            self.buy(bar.symbol, bar.close, self.trade_volume)
```

### Key API

| Method | Description |
|---|---|
| `self.buy(symbol, price, volume)` | Emit a limit buy order |
| `self.sell(symbol, price, volume)` | Emit a limit sell order |
| `self.get_pos(symbol)` | Signed net position (positive=long, 0=flat, negative=short) |
| `self.positions` | `dict[str, PositionData]` updated by engine each bar |
| `self.account` | `AccountData` with current balance |
| `on_trade(trade)` | Called after each fill (override to track fills) |
| `on_stop()` | Called after last bar |

### Multi-symbol strategies

`BacktestEngine` calls `on_bar(bar)` once per bar per symbol, interleaved in chronological order. Use `bar.symbol` to distinguish:

```python
def on_bar(self, bar: BarData) -> None:
    self._history[bar.symbol].append(bar.close)
    # ... compute per-symbol momentum, pick top-K, etc.
```

## Running a Backtest

Data must be cached in SQLite first (via `CachedAkShareFeed.get_bars()` or equivalent). Then:

```python
from src.backtest.engine import BacktestEngine
from src.strategy.examples.ma_cross import MACrossStrategy

engine = BacktestEngine()
result = engine.run(
    strategy=MACrossStrategy(fast_period=5, slow_period=20),
    symbols=["000001.SZ"],
    start="2020-01-01",
    end="2024-12-31",
    interval="daily",
    adjust="qfq",
)
print(result.summary())
# Return=12.34%  Sharpe=0.87  MaxDD=-15.23%  Trades=42  WinRate=52.38%
```

Multi-symbol:

```python
result = engine.run(
    strategy=MomentumRotationStrategy(lookback=20, top_k=3),
    symbols=["000001.SZ", "600036.SH", "000858.SZ"],
    start="2020-01-01",
    end="2024-12-31",
)
```

CLI:

```bash
python run_backtest.py --strategy MACrossStrategy --start 2020-01-01 --end 2024-12-31 --symbols 000001.SZ
# Output: reports/backtest_MACrossStrategy_20240101_120000.html
```

## Technical Indicators (`src/strategy/indicators.py`)

All functions accept `pd.Series` and return `pd.Series` (NaN-padded where insufficient history):

```python
from src.strategy.indicators import sma, ema, rsi, macd, atr, bollinger_bands, momentum

fast = ema(df["close"], 12)
slow = ema(df["close"], 26)

macd_line, signal, hist = macd(df["close"], fast=12, slow=26, signal=9)
rsi_val = rsi(df["close"], 14)
upper, mid, lower = bollinger_bands(df["close"], 20, 2.0)
tr = atr(df["high"], df["low"], df["close"], 14)
mom = momentum(df["close"], 20)
```

**ta-lib backend**: if `ta-lib` C extension is installed, `atr()` and `bollinger_bands()` use it automatically (3-5× faster on large datasets). Install via `conda install ta-lib` or download the binary wheel.

## Parameter Optimization

```python
from src.backtest.optimizer import GridOptimizer
from src.strategy.examples.ma_cross import MACrossStrategy

optimizer = GridOptimizer()
result = optimizer.optimize(
    strategy_cls=MACrossStrategy,
    param_grid={
        "fast_period": [3, 5, 10],
        "slow_period": [15, 20, 30],
        "trade_volume": [100.0],
    },
    symbols=["000001.SZ"],
    start="2020-01-01",
    end="2023-12-31",
    metric="sharpe_ratio",
    n_jobs=4,
)
print(result.best_params)   # {"fast_period": 5, "slow_period": 20, ...}
print(result.best_score)    # 1.23
for params, score in result.top_n(5):
    print(params, score)
```

**Windows spawn-mode safety**: `_run_one` is a module-level function. It receives `(module_path, class_name)` strings and rebuilds the strategy class via `importlib.import_module` inside the subprocess. Never pass class objects directly — spawn cannot pickle dynamically loaded classes.

## HTML Report

```python
from src.backtest.report import generate_report
path = generate_report(result, strategy_name="MACrossStrategy")
# Opens reports/backtest_MACrossStrategy_20240101_120000.html
```

The report includes:
- Equity curve
- Drawdown chart
- Trade scatter plot
- Key metrics in title bar

## Example Strategies

### MACrossStrategy (`ma_cross.py`)
Dual SMA crossover for A-share. Golden cross → long, death cross → short (or flat).

Parameters: `fast_period` (default 5), `slow_period` (default 20), `trade_volume` (100).

### MomentumRotationStrategy (`momentum_rotation.py`)
Ranks symbols by N-day rate-of-change, holds the top-K equal-weighted. Rebalances every N bars.

Parameters: `lookback` (20), `top_k` (2), `rebalance_every` (5), `trade_volume` (100).

### CryptoGridStrategy (`crypto_grid.py`)
Places buy orders at evenly spaced price levels below the entry price. Each filled buy creates a paired sell one grid step above; each filled sell creates a new buy one step below.

Parameters: `grid_step_pct` (0.01 = 1%), `num_grids` (5), `lot_size` (0.01 BTC).

## Running Tests

```bash
pytest tests/unit/test_strategy_base.py   -v
pytest tests/unit/test_indicators.py      -v
pytest tests/unit/test_ma_cross_strategy.py -v
pytest tests/unit/test_momentum_rotation.py -v
pytest tests/                              -v   # all 98 tests
```
