"""CryptoGateway: live crypto trading via ccxt (REST + WebSocket).

Supports 100+ exchanges through a unified interface. Exchange is selected
via config/settings.yaml → gateway.crypto.exchange.

API keys are stored via KeyStore — never plaintext:
    KeyStore().set_key("crypto_api_key", api_key,  master_pwd)
    KeyStore().set_key("crypto_secret",  api_secret, master_pwd)

Usage (REST):
    gw = CryptoGateway()
    gw.on_trade(my_trade_handler)
    gw.connect(api_key=api_key, secret=secret)
    gw.subscribe(["BTC/USDT", "ETH/USDT"])
    order_id = gw.send_order(OrderRequest("BTC/USDT", "LONG", "LIMIT", 50000, 0.01))

Usage (async WebSocket):
    await gw.start_ws(symbols=["BTC/USDT"])   # background task
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from src.core.object import OrderData, TradeData, TickData, BarData, AccountData, PositionData
from src.trading.base_gateway import BaseGateway, OrderRequest
from src.utils.config import get_settings

logger = logging.getLogger(__name__)


class CryptoGateway(BaseGateway):
    """Live crypto gateway backed by ccxt."""

    def __init__(self) -> None:
        super().__init__("crypto")
        cfg = get_settings().gateway.crypto
        self._exchange_id = cfg.exchange
        self._sandbox = cfg.sandbox
        self._exchange = None
        self._ws_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(
        self,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> None:
        try:
            import ccxt  # type: ignore
        except ImportError:
            raise ImportError("ccxt not installed. Run: pip install ccxt")

        exchange_cls = getattr(ccxt, self._exchange_id)
        self._exchange = exchange_cls({
            "apiKey": api_key or "",
            "secret": secret or "",
            "enableRateLimit": True,
        })
        if self._sandbox:
            self._exchange.set_sandbox_mode(True)
        self._exchange.load_markets()
        logger.info(f"CryptoGateway connected to {self._exchange_id} (sandbox={self._sandbox})")

    def disconnect(self) -> None:
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        self._exchange = None
        logger.info("CryptoGateway disconnected")

    def subscribe(self, symbols: list[str]) -> None:
        """Symbols are subscribed when start_ws() is called with the same list."""
        self._subscribed = symbols

    def send_order(self, req: OrderRequest) -> str:
        if self._exchange is None:
            raise RuntimeError("CryptoGateway not connected")

        side = "buy" if req.direction == "LONG" else "sell"
        order_type = req.order_type.lower()

        try:
            resp = self._exchange.create_order(
                symbol=req.symbol,
                type=order_type,
                side=side,
                amount=req.volume,
                price=req.price if order_type == "limit" else None,
            )
        except Exception as e:
            logger.error(f"CryptoGateway order failed: {e}")
            raise

        oid = str(resp["id"])
        req.order_id = oid
        order = OrderData(
            order_id=oid,
            symbol=req.symbol,
            direction=req.direction,
            order_type=req.order_type,
            price=req.price,
            volume=req.volume,
            status="SUBMITTED",
        )
        self.order_book.add(order)
        self.order_book.transition(oid, "ACCEPTED")
        self._on_order(order)
        return oid

    def cancel_order(self, order_id: str) -> None:
        if self._exchange is None:
            return
        order = self.order_book.get(order_id)
        symbol = order.symbol if order else None
        try:
            self._exchange.cancel_order(order_id, symbol)
            if order and self.order_book.transition(order_id, "CANCELLED"):
                self._on_order(order)
        except Exception as e:
            logger.error(f"CryptoGateway cancel failed for {order_id}: {e}")

    def query_account(self) -> AccountData:
        if self._exchange is None:
            return AccountData(balance=0.0, available=0.0)
        balance = self._exchange.fetch_balance()
        total = balance.get("total", {}).get("USDT", 0.0)
        free  = balance.get("free",  {}).get("USDT", 0.0)
        return AccountData(balance=total, available=free)

    def query_position(self, symbol: str) -> PositionData:
        if self._exchange is None:
            return PositionData(symbol=symbol)
        positions = self._exchange.fetch_positions([symbol])
        for p in positions:
            if p.get("symbol") == symbol:
                contracts = p.get("contracts", 0.0) or 0.0
                side = p.get("side", "long")
                net = contracts if side == "long" else -contracts
                return PositionData(
                    symbol=symbol,
                    net_volume=net,
                    avg_price=p.get("entryPrice", 0.0) or 0.0,
                )
        return PositionData(symbol=symbol)

    # ── WebSocket streaming ───────────────────────────────────────────────────

    async def start_ws(self, symbols: list[str]) -> None:
        """Start WebSocket ticker streaming. Run as an asyncio background task."""
        try:
            import ccxt.pro as ccxtpro  # type: ignore
        except ImportError:
            raise ImportError("ccxt[async] not installed. Run: pip install 'ccxt[async]'")

        exchange_cls = getattr(ccxtpro, self._exchange_id)
        exchange = exchange_cls({"enableRateLimit": True})
        if self._sandbox:
            exchange.set_sandbox_mode(True)

        logger.info(f"CryptoGateway WebSocket starting for {symbols}")
        try:
            while True:
                for sym in symbols:
                    try:
                        ticker = await exchange.watch_ticker(sym)
                        ts = int(ticker.get("timestamp", 0) / 1000)
                        tick = TickData(
                            symbol=sym,
                            symbol_id=0,
                            datetime=ts,
                            last_price=ticker.get("last", 0.0),
                            bid_price=ticker.get("bid",  0.0),
                            ask_price=ticker.get("ask",  0.0),
                            volume=ticker.get("baseVolume", 0.0),
                        )
                        self._on_tick(tick)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning(f"CryptoGateway WS tick error ({sym}): {e}")
        finally:
            await exchange.close()
