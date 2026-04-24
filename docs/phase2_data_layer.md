# Phase 2 — Python Data Layer

## Overview

Phase 2 implements the full Python data layer: market data acquisition for three asset classes (A-shares, domestic futures, cryptocurrency), SQLite caching, data quality validation, trading calendar utilities, and configuration management.

## Modules

### `src/data/database.py` — SQLite Cache

Stores OHLCV bars in per-symbol-per-interval tables using WAL journal mode for concurrent reads.

```python
from src.data.database import BarDatabase

db = BarDatabase()                              # defaults to data_cache/bars.db
db.upsert("000001.SZ", "daily", df)            # insert/update rows
df = db.load("000001.SZ", "daily", "2023-01-01", "2024-12-31")
latest = db.latest_date("000001.SZ", "daily")  # returns datetime | None
symbols = db.list_symbols()
```

Table naming convention: `bar_{symbol_safe}_{interval}` where symbol-safe replaces `.`, `/`, and spaces with `_`.

### `src/data/akshare_feed.py` — A-share + Futures Data

**Adjust modes** (controlled by `config/settings.yaml → data.adjust`):
- `qfq` — forward-adjusted (default, use for backtesting; historical prices shift down to match current level)
- `hfq` — backward-adjusted
- `""` — raw/unadjusted (use for live trading to match quoted prices)

**Futures continuous contract** (Panama rollover adjustment):
When the main contract switches, a price gap appears similar to an ex-dividend gap. `_panama_adjust()` detects jumps > 3% and adds a cumulative additive offset to historical bars so the series is continuous. This prevents `DataValidator` from falsely flagging rollover gaps as price anomalies.

```python
from src.data.akshare_feed import CachedAkShareFeed

feed = CachedAkShareFeed()

# A-share with forward-adjustment
df, report = feed.get_bars("000001.SZ", interval="daily", start="2023-01-01")

# Futures main contract (auto-detected, Panama-adjusted)
df, report = feed.get_bars("IF9999", interval="daily", start="2023-01-01")

print(report)  # GREEN / YELLOW / RED badge with counts
```

**Futures symbol detection heuristics** — uppercase, no dot suffix, starts with a known prefix (IF, IC, IH, IM, RB, CU, AU, SC, …).

**Incremental caching**: `CachedAkShareFeed.get_bars()` only downloads missing date ranges. Use `force_refresh=True` to re-download and overwrite the cache (required when changing `adjust` mode).

### `src/data/tushare_feed.py` — Tushare Pro (optional)

Requires a Tushare Pro token. Set via environment variable before use:

```bash
export TUSHARE_TOKEN=your_token_here
```

Or store securely via KeyStore (recommended for production):

```python
from src.utils.keystore import KeyStore
KeyStore().set_key("tushare_token", token, master_password)
```

Then pass to the feed:

```python
from src.data.tushare_feed import TushareFeed
feed = TushareFeed(token="your_token")
df = feed.fetch_bars("000001.SZ", interval="daily", start="20230101", end="20241231")
```

### `src/data/crypto_feed.py` — Cryptocurrency Data (ccxt)

REST history (any exchange ccxt supports) and async WebSocket live ticks.

```python
from src.data.crypto_feed import CryptoFeed, CryptoWebSocketFeed

# Historical bars
feed = CryptoFeed(exchange_id="binance", sandbox=True)
df = feed.fetch_bars("BTC/USDT", interval="1d", start="2023-01-01")

# Real-time ticks (async)
async def on_tick(tick):
    print(tick)

ws = CryptoWebSocketFeed(exchange_id="binance", symbols=["BTC/USDT", "ETH/USDT"])
await ws.start(on_tick)
```

Supported exchanges: any ccxt-supported exchange (binance, okx, bybit, gate, …). Set `sandbox=True` for testnet.

API keys are **never** stored in config files. Pass them via KeyStore at startup:

```python
api_key = KeyStore().get_key("crypto_api_key", master_password)
secret   = KeyStore().get_key("crypto_secret",  master_password)
feed = CryptoFeed("binance", api_key=api_key, secret=secret)
```

### `src/data/data_validator.py` — Data Quality Validation

Validates OHLCV DataFrames and returns a `ValidationReport` with a green/yellow/red badge.

Checks performed:
1. **Missing values** — NaN rows counted; missing ratio > 1% → yellow
2. **OHLC consistency** — `high >= max(open, close)` and `low <= min(open, close)`
3. **Price anomalies** — single-day close change exceeding asset-type threshold
4. **Zero-volume days** — days with volume = 0 (suspension / delisting risk)

**Thresholds are configured in `config/settings.yaml`** — never hardcoded:

```yaml
validator_thresholds:
  stock:              0.11   # A-share (incl. STAR/ChiNext ±20%)
  futures_commodity:  0.06   # commodity futures (most ±5%, +1% buffer)
  futures_index:      0.11   # CSI 300/500/1000 futures ±10%
  futures_energy:     0.16   # crude oil ±15%
  crypto:             1.0    # no limit; statistical model catches true anomalies
```

```python
from src.data.data_validator import DataValidator
validator = DataValidator()
report = validator.validate(df, "000001.SZ", asset_type="stock")
print(report.badge)          # "GREEN" | "YELLOW" | "RED"
print(report.ok)             # True if badge != RED
print(report.price_anomalies)  # list of (date, pct_change) tuples
```

### `src/utils/calendar.py` — Trading Calendar

```python
from src.utils.calendar import TradingCalendar
from datetime import datetime, date

TradingCalendar.is_ashare_trading(datetime(2024, 3, 15, 9, 45))   # True
TradingCalendar.is_ashare_trading(datetime(2024, 3, 15, 12, 0))   # False (lunch)
TradingCalendar.is_crypto_trading(datetime(2024, 1, 1, 0, 0))     # True (24/7)

dates = TradingCalendar.trading_dates_in_range(date(2024, 3, 11), date(2024, 3, 15))
next_d = TradingCalendar.next_trading_day(date(2024, 3, 15))      # 2024-03-18
```

A-share session hours: 09:30–11:30 and 13:00–15:00. Weekends excluded. Public holiday list is a curated set; update `ASHARE_HOLIDAYS` in `calendar.py` annually.

### `src/utils/config.py` — Configuration

Settings are loaded from `config/settings.yaml` with pydantic validation and LRU-cached:

```python
from src.utils.config import get_settings
s = get_settings()
s.backtest.initial_capital   # 1_000_000.0
s.risk.max_position_pct      # 0.20
s.validator_thresholds       # dict[str, float]
```

To reload after a YAML change (e.g., in tests):

```python
from src.utils.config import reload_settings
reload_settings()
```

## Configuration Reference (`config/settings.yaml`)

```yaml
system:
  mode: backtest        # backtest | paper | live
  log_level: INFO

data:
  adjust: qfq           # qfq | hfq | "" (unadjusted for live)

backtest:
  initial_capital: 1000000
  commission_rate: 0.0003
  slippage: 0.001

risk:
  max_position_pct: 0.20
  daily_loss_limit: 0.02
  max_drawdown: 0.10

validator_thresholds:
  stock: 0.11
  futures_commodity: 0.06
  futures_index: 0.11
  futures_energy: 0.16
  crypto: 1.0
```

## Running Tests

```bash
pytest tests/unit/test_database.py       -v   # SQLite cache
pytest tests/unit/test_data_validator.py -v   # validation
pytest tests/unit/test_akshare_panama.py -v   # futures Panama rollover
pytest tests/unit/test_config.py         -v   # settings
pytest tests/unit/test_calendar.py       -v   # trading calendar
pytest tests/unit/test_keystore.py       -v   # API key encryption
pytest tests/                            -v   # all 70 tests
```

## Data Quality Workflow

1. Download bars via `CachedAkShareFeed.get_bars()` or `CryptoFeed.fetch_bars()`
2. `ValidationReport` is returned alongside the DataFrame
3. Check `report.badge`: GREEN = ready, YELLOW = review anomalies, RED = do not use for backtest
4. Validation issues are logged to `logs/data_quality.log`
5. GUI data management page (Phase 5) displays the badge per symbol

## Notes

- Changing `adjust` mode requires `force_refresh=True` on next `get_bars()` call to overwrite cached raw-price data
- Futures Panama adjustment is applied in-memory only; the SQLite cache stores raw unadjusted prices so rollover offset can be recalculated on each load
- `TushareFeed` and `CryptoFeed` require network access; unit tests mock the external calls
