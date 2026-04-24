# Phase 1: Rust Core Engine

## Module Overview

| File | Role |
|---|---|
| `core_engine/src/object.rs` | Data structures: Bar, Tick, Order, Trade, Position |
| `core_engine/src/event.rs` | EventEngine: lockless MPMC queue (crossbeam), multi-thread dispatch |
| `core_engine/src/broker.rs` | SimBroker: full match simulation (price limit, slippage, commission, partial fills) |
| `core_engine/src/risk.rs` | RiskManager: position limit, daily loss limit, order volume cap |
| `core_engine/src/backtest.rs` | BacktestRunner: cash+M2M equity accounting, GIL-held batch loop |
| `core_engine/src/bar_builder.rs` | BarBuilder: Tick → multi-period OHLCV Bar synthesis |
| `core_engine/src/metrics.rs` | MetricsEngine: Sharpe, Sortino, MaxDrawdown, Calmar, win rate, profit factor |
| `core_engine/src/lib.rs` | PyO3 entry: registers all Python-callable classes |

## PyO3 API Reference

### `Bar(symbol_id, datetime, open, high, low, close, volume)`
```python
from quant_core import Bar
b = Bar(0, 1_700_000_000, 10.0, 10.5, 9.8, 10.2, 5_000.0)
print(b.close, b.symbol_id)
```

### `Tick(symbol_id, datetime, last_price, bid_price, ask_price, volume)`

### `EventEngine()`
```python
from quant_core import EventEngine
e = EventEngine()
e.start()
e.put_bar(b)  # non-blocking enqueue
e.stop()
```

### `BrokerConfigPy(...)`
```python
from quant_core import BrokerConfigPy
cfg = BrokerConfigPy(
    commission_rate=0.0003,
    slippage=0.001,
    price_limit_pct=0.10,        # A-share ±10% limit
    initial_capital=1_000_000.0,
    max_position_pct=0.20,
    daily_loss_limit=0.02,
    max_order_volume=1_000.0,
    max_fill_volume_per_bar=0.0, # 0 = fill entire order in one bar
)
```

### `BacktestRunner(config, strategy_on_bar, strategy_on_trade)`
```python
from quant_core import BacktestRunner

def on_bar(bar):
    # Return list of order tuples: (symbol_id, is_long, is_limit, price, volume)
    if bar.close > some_ma:
        return [(bar.symbol_id, True, False, 0.0, 100.0)]  # market buy
    return []

def on_trade(trade_id, order_id, symbol_id, is_long, price, volume, commission, datetime):
    # Called synchronously after each fill
    pass

runner = BacktestRunner(cfg, on_bar, on_trade)
metrics = runner.run_batch(bars)  # bars: list[Bar], sorted by datetime
print(metrics)
print(runner.get_positions())     # [(symbol_id, net_vol, avg_price, upnl, rpnl), ...]
print(runner.current_equity())
```

### `BacktestMetrics` (returned by `run_batch`)
| Attribute | Type | Description |
|---|---|---|
| `total_return` | float | e.g. 0.15 = +15% |
| `annualized_return` | float | Annualised assuming daily bars |
| `sharpe` | float | Annualised Sharpe (rf=2%) |
| `sortino` | float | Sortino ratio (downside std only) |
| `max_drawdown` | float | e.g. -0.12 = -12% |
| `calmar` | float | annualised\_return / abs(max\_drawdown) |
| `win_rate` | float | Fraction of trades with net\_pnl > 0 |
| `profit_factor` | float | gross\_profit / gross\_loss |
| `total_trades` | int | Total fills (opens + closes) |
| `initial_capital` | float | |
| `final_equity` | float | cash + market value at last bar |

## GIL Policy

| Path | GIL behaviour | Why |
|---|---|---|
| `BacktestRunner.run_batch()` | Held for entire loop | Single-thread batch; no Rust threads blocked |
| `EventEngine` (live) | Acquire per callback, release immediately | Rust threads must not be blocked long-term |

**Never mix these two patterns.** The live EventEngine registers Python callbacks that are called inside Rust threads; each callback acquires GIL on entry and releases on exit to keep other Rust threads unblocked.

## Key Design Decisions

### Cash + Market Value Equity Accounting
Equity is tracked as `cash + Σ(net_volume × latest_price)`, **not** as incremental M2M deltas.
This prevents double-counting when a closing trade triggers both a cash inflow and a realized P&L calculation.

### SymbolRegistry (Python ↔ Rust)
`Bar.symbol_id: u32` keeps Rust structs fixed-width (numpy-compatible).
Python maintains `SymbolRegistry` for bidirectional mapping.
```python
from src.core.object import SymbolRegistry
sid = SymbolRegistry.get_or_register("000001.SZ")  # → 0
sym = SymbolRegistry.lookup(0)                      # → "000001.SZ"
```

### Multi-Symbol: Interleaved Bars
For multi-symbol backtests, sort bars by datetime before calling `run_batch`. Python handles alignment; Rust processes the flat interleaved sequence.
```python
merged = pd.concat([df_sym0.assign(symbol_id=0), df_sym1.assign(symbol_id=1)])
merged = merged.sort_values("datetime")
bars = [Bar(**row) for _, row in merged.iterrows()]
```

### Partial Fills
Set `max_fill_volume_per_bar > 0` in `BrokerConfigPy` to simulate partial fills (useful for illiquid symbols or large orders):
```python
cfg = BrokerConfigPy(max_fill_volume_per_bar=200.0)  # max 200 shares per bar
```

## Running Tests

```bash
# Rust unit tests (25 tests)
cargo test --manifest-path core_engine/Cargo.toml

# Rebuild Python extension
maturin build --release
pip install core_engine/target/wheels/quant_trade-*.whl --force-reinstall

# Python tests (31 tests: unit + integration)
pytest tests/
```

## Adding a New Rust Module

1. Create `core_engine/src/new_module.rs`
2. Add `mod new_module;` to `lib.rs`
3. If it needs Python exposure: `m.add_class::<new_module::MyClass>()?;` in `quant_core()`
4. Add tests in `#[cfg(test)] mod tests { ... }` at bottom of the file
5. Run `cargo test` to verify, then rebuild with `maturin build --release`
