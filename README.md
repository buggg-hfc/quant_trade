# quant_trade

Automated quantitative trading system supporting A-shares, domestic futures, and cryptocurrency. Rust core engine (PyO3/maturin) for performance-critical logic; Python for strategies, scheduling, and GUI.

## Quick Start

```bash
# Windows
setup.bat

# Linux / macOS
bash setup.sh

# Start GUI + live server
python launcher.py
# → Streamlit dashboard: http://localhost:8501
# → Live dashboard:      http://localhost:8000
```

## Architecture

```
Python (strategy/GUI/scheduling)
  └─ BacktestEngine  ──→  Rust BacktestRunner.run_batch()  [GIL held once per batch]
  └─ LiveEngine      ──→  Rust EventEngine  [per-callback GIL acquire/release]
  └─ Streamlit GUI   ──→  FastAPI WebSocket live dashboard
  └─ RiskManager     ──→  Rust RiskManager (fast rules) + Python RiskManager (business rules)
```

| Layer | Technology |
|---|---|
| Performance core | Rust + PyO3 + maturin (`quant_core` extension) |
| A-share / futures data | akshare (free), tushare pro (optional) |
| Crypto data | ccxt (100+ exchanges) |
| Technical indicators | `ta` library (ta-lib optional backend) |
| Strategy framework | `BaseStrategy` ABC, `strategies/` hot-reload |
| Backtest | Multi-symbol, Rust-accelerated, Panama rollover |
| Parameter optimization | `GridOptimizer`, spawn-safe multiprocessing |
| Live gateways | PaperGateway, CTPGateway, XTPGateway (optional), CryptoGateway |
| Risk management | Python rules chain → Rust fast filter |
| GUI | Streamlit (8 pages) + FastAPI WebSocket live dashboard |
| Alerts | Email (smtplib) + WeChat Work webhook |
| Key storage | Fernet encryption, PBKDF2-derived, SQLite |
| Deployment | Windows Service, Task Scheduler, PyInstaller |

## Directory Structure

```
quant_trade/
├── core_engine/          Rust core (EventEngine, SimBroker, BacktestRunner, metrics)
├── src/
│   ├── core/             SymbolRegistry, MainEngine
│   ├── data/             akshare, tushare, ccxt, SQLite cache, DataValidator
│   ├── strategy/         BaseStrategy, indicators, examples
│   ├── backtest/         BacktestEngine, GridOptimizer, Plotly report
│   ├── trading/          BaseGateway + OMS, Paper/CTP/XTP/Crypto gateways
│   ├── risk/             RiskManager + composable rules
│   ├── monitor/          Streamlit dashboard, FastAPI live server, notifier
│   └── utils/            config, calendar, keystore, logger
├── strategies/           User strategy files (GUI-managed, hot-loaded)
├── config/settings.yaml  All configuration (no secrets)
├── config/.env           KEYSTORE_SALT only (gitignored)
├── tests/                125 unit + integration tests
├── docs/                 Per-phase README files
├── scripts/              Windows Service + Task Scheduler setup
├── launcher.py           Process manager (Streamlit + FastAPI)
├── run_backtest.py       CLI backtest
├── run_live.py           CLI live trading
├── setup.bat / setup.sh  One-click install
├── run_gui.bat           Double-click launcher (Windows)
└── quant_trade.spec      PyInstaller packaging spec
```

## CLI Usage

```bash
# Backtest
python run_backtest.py --strategy MACrossStrategy --symbol 000001.SZ --start 2020-01-01

# Live trading (paper simulation)
python run_live.py --gateway paper --strategy MACrossStrategy

# Crypto (testnet)
python run_live.py --gateway crypto --exchange binance --sandbox true --strategy CryptoGridStrategy

# Tests
pytest tests/ -v
```

## Writing a Strategy

```python
# strategies/my_strategy.py
from src.strategy.base import BaseStrategy
from src.core.object import BarData

class MyStrategy(BaseStrategy):
    fast_period: int = 5    # class-level int/float → GUI parameter
    trade_volume: float = 100.0

    def on_bar(self, bar: BarData) -> None:
        if self.get_pos(bar.symbol) == 0:
            self.buy(bar.symbol, bar.close, self.trade_volume)
```

## Security

- All API keys and passwords stored via `KeyStore` (Fernet + PBKDF2HMAC, SQLite)
- `settings.yaml` contains only non-secret parameters (IPs, exchange IDs, account names)
- `config/.env` contains only `KEYSTORE_SALT` — never actual secrets

## Documentation

Phase-by-phase READMEs in `docs/`:
- `phase0_setup.md` — environment, Rust toolchain, maturin
- `phase1_core_engine.md` — Rust modules, PyO3 bindings, GIL policy
- `phase2_data_layer.md` — data feeds, SQLite cache, validation
- `phase3_backtest_strategy.md` — strategy framework, backtest engine, optimizer
- `phase4_risk_gateways.md` — risk rules, gateways, OMS
- `phase5_monitor_deploy.md` — GUI, live server, Windows deployment
