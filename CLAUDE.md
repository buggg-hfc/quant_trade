# quant_trade — Claude Code Context

## Architecture Overview
- Rust core (`core_engine/`) exposed as `quant_core` Python extension via PyO3/maturin
- Python handles strategy/scheduling/GUI; Rust handles EventEngine/backtest loop/matching/risk/metrics
- GIL acquired once at `BacktestRunner.run_batch()` entry, held for the entire loop (backtest only)

## Build Commands
```
cd core_engine && cargo test          # Rust unit tests
maturin develop --release             # Compile and install quant_core into current venv
pytest tests/                         # Python tests
```

## Start Commands
```
python launcher.py                    # Start Streamlit(:8501) + FastAPI(:8000)
python launcher.py --gui-only         # Streamlit only
python launcher.py --live-only        # FastAPI only (after manual position confirmation)
```

## Key Conventions
- New strategies go in `strategies/`, inherit `BaseStrategy`, class-level int/float attrs auto-become GUI params
- All secrets (password/api_key/secret) via `KeyStore.set_key()` → encrypted SQLite; `settings.yaml` holds only non-secret connection params (IP/port/account name); `.env` holds only `KEYSTORE_SALT` and similar non-secret config
- akshare default adjust=`qfq` (forward-adjusted, for backtest); live gateways use `""` (raw price)
- `BacktestRunner` requires both `strategy_on_bar` and `strategy_on_trade` callbacks
- Windows `multiprocessing` uses `spawn`; `optimizer.py` entry must have `if __name__=="__main__"` guard
- `optimizer._run_one()` passes `(module_path, class_name)` strings; subprocess uses `importlib` to reload the strategy class — never pass the class object itself (spawn cannot pickle dynamically loaded classes)
- `Bar.symbol` in Rust is `symbol_id: u32`; Python uses `SymbolRegistry` for bidirectional mapping; never store `String` symbol in Rust (incompatible with numpy structured array memory layout)
- **GIL policy**: `run_batch()` holds GIL for the entire batch loop (backtest-only, single-threaded, acceptable); live `EventEngine` acquire/release GIL per callback — never hold long-term, to keep Rust threads unblocked. Do NOT mix these two patterns.
- FastAPI (live server) **must NOT auto-restart on crash** — alert only; live positions may be in memory. Manual restart after confirming positions: `python launcher.py --live-only`
- Data validation thresholds are per asset-type in `settings.yaml` `validator_thresholds`; never hardcode ±N% in Python

## Do Not Touch
- `config/.env` (secrets, gitignored)
- `data_cache/` (SQLite cache, gitignored)
