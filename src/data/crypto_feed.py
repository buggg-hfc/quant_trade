"""Crypto data feed via ccxt (REST history + WebSocket real-time ticks).

Supports 100+ exchanges through ccxt's unified interface.
Default exchange: Binance. Switch via exchange_id.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Optional

import pandas as pd

from src.data.base import BaseDataFeed

logger = logging.getLogger(__name__)

# ccxt timeframe labels
_INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
    "daily": "1d", "1d": "1d", "1w": "1w", "1M": "1M",
}


class CryptoFeed(BaseDataFeed):
    """Unified crypto feed (REST history) backed by ccxt."""

    def __init__(self, exchange_id: str = "binance", sandbox: bool = False) -> None:
        self._exchange_id = exchange_id
        self._sandbox = sandbox
        self._exchange = None

    def name(self) -> str:
        return f"ccxt_{self._exchange_id}"

    def _get_exchange(self):
        if self._exchange is None:
            try:
                import ccxt
            except ImportError:
                raise ImportError("ccxt not installed. Run: pip install ccxt")
            cls = getattr(ccxt, self._exchange_id)
            self._exchange = cls({"enableRateLimit": True})
            if self._sandbox:
                self._exchange.set_sandbox_mode(True)
        return self._exchange

    def fetch_bars(
        self,
        symbol: str,
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust: str = "",  # crypto has no adjust
    ) -> pd.DataFrame:
        ex = self._get_exchange()
        timeframe = _INTERVAL_MAP.get(interval, interval)
        if not ex.has["fetchOHLCV"]:
            raise RuntimeError(f"{self._exchange_id} does not support OHLCV")

        since_ms = None
        if start:
            since_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

        all_bars: list[list] = []
        limit = 1000

        while True:
            bars = ex.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
            if not bars:
                break
            all_bars.extend(bars)
            if len(bars) < limit:
                break
            since_ms = bars[-1][0] + 1
            time.sleep(ex.rateLimit / 1000)

        if not all_bars:
            return pd.DataFrame()

        df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
        df = df.set_index("date").drop(columns=["timestamp"]).sort_index()

        if end:
            end_dt = pd.to_datetime(end)
            df = df[df.index <= end_dt]

        return df


class CryptoWebSocketFeed:
    """Real-time tick stream from ccxt WebSocket (async)."""

    def __init__(self, exchange_id: str = "binance", sandbox: bool = False) -> None:
        self._exchange_id = exchange_id
        self._sandbox = sandbox

    async def stream_ticks(
        self,
        symbol: str,
        on_tick: Callable[[dict], None],
    ) -> None:
        """Stream live ticks and call on_tick for each update.

        on_tick receives a dict: {symbol, datetime, last, bid, ask, volume}

        Requires ccxt[async] support (ccxt.pro / ccxt 4.x).
        """
        try:
            import ccxt.pro as ccxtpro
        except ImportError:
            raise ImportError("ccxt[async] not available. Run: pip install ccxt[async]")

        cls = getattr(ccxtpro, self._exchange_id)
        exchange = cls({"enableRateLimit": True})
        if self._sandbox:
            exchange.set_sandbox_mode(True)

        try:
            while True:
                ticker = await exchange.watch_ticker(symbol)
                on_tick({
                    "symbol": symbol,
                    "datetime": datetime.utcnow(),
                    "last": ticker.get("last", 0.0),
                    "bid": ticker.get("bid", 0.0),
                    "ask": ticker.get("ask", 0.0),
                    "volume": ticker.get("baseVolume", 0.0),
                })
        except asyncio.CancelledError:
            logger.info(f"WebSocket stream for {symbol} cancelled")
        finally:
            await exchange.close()
