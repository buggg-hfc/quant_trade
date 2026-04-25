# Phase 5 — Monitoring, GUI & Deployment

## Overview

Phase 5 delivers the full production system: Streamlit 8-page dashboard, FastAPI + WebSocket live server, a lightweight real-time HTML UI, alert notifications, Windows Task Scheduler integration, Windows Service support, and PyInstaller packaging.

## Starting the System

```bash
# Start everything (Streamlit on :8501, FastAPI on :8000)
python launcher.py

# GUI only (no live server)
python launcher.py --gui-only

# Live server only (after confirming positions following a crash)
python launcher.py --live-only
```

Double-click `run_gui.bat` on Windows for a no-terminal startup.

### Crash policy

| Process | Crash action |
|---|---|
| Streamlit (GUI) | Auto-restart — stateless, safe |
| FastAPI (live server) | **Alert only — no auto-restart**. Live positions may be in memory. Restart manually with `python launcher.py --live-only` after confirming positions. |

## Streamlit Dashboard (`src/monitor/dashboard.py`)

Navigate via the sidebar:

| Page | Description |
|---|---|
| **Home** | System status, mode, capital, directory health check |
| **Data** | Download A-share/futures/crypto bars, view cache contents |
| **Strategies** | CRUD: list, edit, create, archive strategy files |
| **Backtest** | Run single backtest or parameter grid search (background thread) |
| **Live Trading** | Configure API keys (via KeyStore), start/stop strategies |
| **Risk** | View/edit risk thresholds in settings.yaml |
| **Logs** | Tail application and data quality logs; test alert delivery |
| **Help** | Embedded README and quick command reference |

## FastAPI Live Server (`src/monitor/live_server.py`)

WebSocket broadcast endpoint: `ws://localhost:8000/ws`

REST endpoints:
- `GET /` — serve the live UI HTML page
- `GET /state` — current system snapshot (account, positions, orders, trades)
- `GET /health` — uptime check

Publisher functions (call from live trading engine):

```python
from src.monitor.live_server import (
    publish_account, publish_position, publish_order, publish_trade, publish_tick, set_status
)

publish_account(balance=1_050_000, available=900_000, pnl=50_000)
publish_trade("IF2412", "LONG", 3800.0, 1.0, commission=11.4)
set_status("live", gateway="ctp")
```

## Live UI (`src/monitor/live_ui/index.html`)

Minimal dark-theme HTML+JS dashboard that consumes the WebSocket feed. Features:
- Auto-reconnects on disconnect (3s retry)
- Snapshot on connect (no missed events)
- Tables: positions, open orders, last 50 trades
- Metric cards: balance, available, P&L, position count

Served automatically at `http://localhost:8000/` by the FastAPI server.

## Alert Notifier (`src/monitor/notifier.py`)

```python
from src.monitor.notifier import Notifier
notifier = Notifier.from_settings(email_password="xxx")
notifier.alert("Trade filled", "BUY IF2412 @3800 × 1")
```

Configure in `config/settings.yaml`:

```yaml
notifier:
  email:
    smtp_host: smtp.qq.com
    port: 465
    sender: your@qq.com
    receiver: alert@yourcompany.com
  wechat_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
```

Email password goes through KeyStore:
```python
KeyStore().set_key("email_password", password, master_pwd)
```

## CLI Scripts

```bash
# Backtest
python run_backtest.py --strategy MACrossStrategy --symbol 000001.SZ --start 2020-01-01
# Output: reports/backtest_MACrossStrategy_2020.html

# Live trading
python run_live.py --gateway paper --strategy MACrossStrategy
python run_live.py --gateway crypto --exchange binance --sandbox true --strategy CryptoGridStrategy
python run_live.py --gateway ctp --strategy MACrossStrategy
```

## Windows Task Scheduler (`scripts/scheduler_setup.py`)

Run as Administrator:

```cmd
python scripts/scheduler_setup.py --install            # A-share: start 09:25, stop 15:05 Mon-Fri
python scripts/scheduler_setup.py --install --crypto   # also add 24/7 crypto restart task
python scripts/scheduler_setup.py --remove             # remove all tasks
```

Tasks created:
- `QuantTrade_AShare_Start` — starts `python launcher.py` at 09:25 Mon–Fri
- `QuantTrade_AShare_Stop` — kills Python processes at 15:05 Mon–Fri
- `QuantTrade_Crypto_24x7` — (optional) restarts `python launcher.py --live-only` daily at 00:01

## Windows Service (`scripts/install_service.py`)

Registers the FastAPI live server as a Windows Service (auto-start on boot):

```cmd
python scripts/install_service.py --install   # requires Administrator
python scripts/install_service.py --start
python scripts/install_service.py --stop
python scripts/install_service.py --remove
```

Requires `pip install pywin32`.

## PyInstaller Packaging (`quant_trade.spec`)

Build a standalone executable (no Python installation required on target machine):

```bash
# Step 1: compile Rust extension first
maturin develop --release

# Step 2: bundle
pyinstaller quant_trade.spec

# Output: dist/quant_trade.exe (Windows) or dist/quant_trade (Linux/macOS)
```

**Important:** test the bundle on a **clean Windows machine** (no Python/Rust/VS installed) to verify:
- `quant_core.pyd` loads without `ImportError: DLL load failed`
- MSVC runtime DLLs (`vcruntime140.dll`, `msvcp140.dll`) are bundled
- Streamlit assets are included

Update `quant_trade.spec → binaries` if DLL paths differ on your system.

## Full End-to-End Flow (new user, 30 minutes)

1. Clone the repo and run `setup.bat` (Windows) or `setup.sh` (Linux/macOS)
2. Double-click `run_gui.bat` → browser opens at `http://localhost:8501`
3. **Data page**: download 000001.SZ bars (akshare, free, no account needed)
4. **Backtest page**: select MACrossStrategy → Run Backtest → view metrics + equity curve
5. **Live Trading page**: select Paper gateway → copy the CLI command shown → run in terminal
6. Open `http://localhost:8000` to see the real-time live dashboard
7. **Logs page**: verify no errors

## Full Test Suite

```bash
pytest tests/ -v   # 125 tests
```
