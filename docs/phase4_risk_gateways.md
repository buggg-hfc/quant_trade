# Phase 4 — Risk Management & Live Gateways

## Overview

Phase 4 adds the Python risk layer and four concrete gateways (Paper, CTP, XTP, Crypto) that share a common abstract interface. The risk layer sits upstream of every order, chaining Python business rules with the Rust fast-filter.

## Risk Layer

### `src/risk/rules.py` — Individual Rules

Rules are composable callables: `(OrderData, AccountData, positions) → (bool, str)`.

| Rule | Description |
|---|---|
| `blacklist_rule(symbols)` | Reject orders for blacklisted symbols |
| `max_position_rule(pct)` | Reject if new position would exceed `pct × balance` |
| `daily_loss_rule(pct)` | Halt all orders when cumulative loss exceeds `pct × balance` |
| `max_order_volume_rule(max)` | Reject single orders larger than `max` lots |

### `src/risk/manager.py` — RiskManager

```python
from src.risk.manager import RiskManager

rm = RiskManager(blacklist={"ST_RISK.SZ", "HALT.SZ"})
result = rm.check(order, account, positions)
if not result:
    logger.warning(f"Blocked: {result.reason}")
    return
gateway.send_order(order_request)
```

Configuration is read from `config/settings.yaml`:

```yaml
risk:
  max_position_pct: 0.20      # max 20% of account per symbol
  daily_loss_limit: 0.02      # halt if intraday P&L < -2%
  max_order_volume: 1000.0    # reject orders > 1 000 lots
```

To add custom rules:

```python
def regulatory_rule(order, account, positions):
    if order.symbol.endswith(".SZ") and order.volume > 500:
        return False, "SZ exchange single-order volume cap"
    return True, ""

rm.add_rule(regulatory_rule)
```

### Two-pass risk architecture (live mode)

```
OrderRequest
  → Python RiskManager   (blacklist, position pct, daily loss, custom rules)
  → Rust RiskManager     (fast: position count, daily loss counter, max volume)
  → Gateway.send_order()
```

## Gateways

All gateways implement `BaseGateway`:

```python
gw.connect(...)
gw.subscribe(symbols)
order_id = gw.send_order(OrderRequest(symbol, direction, order_type, price, volume))
gw.cancel_order(order_id)
account = gw.query_account()    # → AccountData
pos     = gw.query_position(s)  # → PositionData
gw.disconnect()
```

Register callbacks before connecting:

```python
gw.on_trade(lambda t: print(f"Fill: {t.symbol} {t.direction} {t.volume}@{t.price}"))
gw.on_order(lambda o: print(f"Order {o.order_id}: {o.status}"))
gw.on_tick(lambda tick: ...)
gw.on_bar(lambda bar: ...)
```

### OMS (Order Management System)

Built into `BaseGateway.order_book`. Valid state transitions:

```
SUBMITTED → ACCEPTED → PARTIAL → FILLED
          ↘ REJECTED    ↘ CANCELLED
```

```python
gw.order_book.open_orders()     # [OrderData, ...] with status SUBMITTED/ACCEPTED/PARTIAL
gw.order_book.get(order_id)     # OrderData | None
gw.order_book.all_orders()      # all orders including terminal states
```

### PaperGateway (`src/trading/paper_gateway.py`)

Simulated matching engine for paper trading and integration tests. Interface-identical to live gateways — swap with one config change.

```python
from src.trading.paper_gateway import PaperGateway
from src.trading.base_gateway import OrderRequest

gw = PaperGateway(initial_capital=1_000_000.0)
gw.on_trade(lambda t: print(t))
gw.connect()
gw.subscribe(["000001.SZ"])

# In a bar loop:
gw.send_order(OrderRequest("000001.SZ", "LONG", "LIMIT", price=10.5, volume=100.0))
gw.process_bar(bar)   # triggers matching; fills emit on_trade callbacks
```

Matching rules:
- **Limit buy**: fills at bar open if `open ≤ order.price`
- **Limit sell**: fills at bar open if `open ≥ order.price`
- **Market**: fills at open ± slippage
- **Price-limit**: pending buys cancelled if `close ≥ prev_close × (1 + limit_pct)`, sells if `close ≤ prev_close × (1 - limit_pct)`
- Commission and slippage taken from `settings.yaml → backtest`

### CTPGateway (`src/trading/ctp_gateway.py`)

CTP futures live trading via `openctp-ctp`.

**Prerequisites:**
1. CTP broker account (SimNow for simulation: tcp://180.168.146.187:10201)
2. `pip install openctp-ctp`
3. Store password via KeyStore (never in config files)

```python
from src.utils.keystore import KeyStore
from src.trading.ctp_gateway import CTPGateway

password = KeyStore().get_key("ctp_password", master_pwd)
gw = CTPGateway()
gw.on_trade(handler)
gw.connect(password=password)
gw.subscribe(["IF2412", "RB2501"])
```

**settings.yaml** (non-secret params only):

```yaml
gateway:
  ctp:
    broker_id: "9999"             # SimNow broker ID
    user_id: "your_account"
    td_address: "tcp://180.168.146.187:10201"
    md_address: "tcp://180.168.146.187:10211"
```

### XTPGateway (`src/trading/xtp_gateway.py`) — Optional

A-share live trading via XTP SDK (ZhongTai Securities / 中泰证券).

**Prerequisites (step 1 before development):**
1. Open an account with 中泰证券 (ZhongTai Securities).
2. Apply for XTP API access: contact your account manager or visit their developer portal.
3. Approval typically takes 1–2 weeks.
4. `pip install xtpwrapper` (or official XTP Python binding)

Until SDK access is granted, use `PaperGateway` — the interface is identical.

```python
from src.trading.xtp_gateway import XTPGateway, _XTP_AVAILABLE
if not _XTP_AVAILABLE:
    from src.trading.paper_gateway import PaperGateway as XTPGateway
```

**settings.yaml** (non-secret params):

```yaml
gateway:
  xtp:
    server_ip: "120.xxx.xxx.xxx"
    server_port: 24800
    account: "your_account"
    client_id: 1
```

### CryptoGateway (`src/trading/crypto_gateway.py`)

Live crypto trading via ccxt (REST) with async WebSocket streaming.

```python
from src.utils.keystore import KeyStore
from src.trading.crypto_gateway import CryptoGateway
from src.trading.base_gateway import OrderRequest

api_key = KeyStore().get_key("crypto_api_key", master_pwd)
secret  = KeyStore().get_key("crypto_secret",  master_pwd)

gw = CryptoGateway()   # uses settings.yaml → gateway.crypto.exchange
gw.on_trade(handler)
gw.connect(api_key=api_key, secret=secret)
gw.subscribe(["BTC/USDT"])
gw.send_order(OrderRequest("BTC/USDT", "LONG", "LIMIT", 50_000.0, 0.01))

# Async WebSocket streaming (run in asyncio event loop):
import asyncio
asyncio.run(gw.start_ws(["BTC/USDT", "ETH/USDT"]))
```

**settings.yaml:**

```yaml
gateway:
  crypto:
    exchange: binance   # binance | okx | bybit | gate | …
    sandbox: true       # use testnet
```

## API Key Security

**All credentials (passwords, API keys, secrets) go through KeyStore — never in any config file.**

```python
from src.utils.keystore import KeyStore
ks = KeyStore()
ks.set_key("ctp_password",    plaintext, master_pwd)
ks.set_key("crypto_api_key",  plaintext, master_pwd)
ks.set_key("crypto_secret",   plaintext, master_pwd)
ks.set_key("xtp_password",    plaintext, master_pwd)
```

`settings.yaml` holds only non-secret connection parameters (IP, port, account name, exchange ID).

## Running Tests

```bash
pytest tests/unit/test_risk_manager.py  -v   # 14 tests
pytest tests/unit/test_paper_gateway.py -v   # 13 tests
pytest tests/                            -v   # all 125 tests
```

CTP, XTP, and Crypto gateway tests require live credentials and network access — they are integration tests excluded from the default test suite.
