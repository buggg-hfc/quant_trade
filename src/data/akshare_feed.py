"""AkShare data feed for A-share and domestic futures.

Adjust modes:
    qfq  — forward-adjusted (default, for backtest)
    hfq  — backward-adjusted
    ""   — unadjusted (for live trading, matches quoted price)

Futures rollover (Panama method):
    Main-contract switches cause price jumps similar to ex-dividend gaps.
    We apply a cumulative additive offset per rollover so the series is
    continuous, preventing data_validator from falsely flagging the gap.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.data.base import BaseDataFeed
from src.data.database import BarDatabase
from src.data.data_validator import DataValidator, ValidationReport

logger = logging.getLogger(__name__)


class AkShareFeed(BaseDataFeed):
    """Historical bar data via akshare (A-share daily/minute + futures)."""

    def name(self) -> str:
        return "akshare"

    def fetch_bars(
        self,
        symbol: str,
        interval: str = "daily",
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare not installed. Run: pip install akshare")

        end = end or datetime.today().strftime("%Y%m%d")
        start = start or "20150101"

        # Normalise date format for akshare (YYYYMMDD, no dashes)
        start_ak = start.replace("-", "")
        end_ak = end.replace("-", "")

        if self._is_futures(symbol):
            return self._fetch_futures(ak, symbol, start_ak, end_ak)
        else:
            return self._fetch_ashare(ak, symbol, start_ak, end_ak, adjust, interval)

    # ── A-share ───────────────────────────────────────────────────────────────

    def _fetch_ashare(
        self, ak, symbol: str, start: str, end: str, adjust: str, interval: str
    ) -> pd.DataFrame:
        code = symbol.split(".")[0]  # "000001.SZ" → "000001"
        adj_map = {"qfq": "qfq", "hfq": "hfq", "": ""}
        adj_param = adj_map.get(adjust, "qfq")

        if interval in ("daily", "1d"):
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start, end_date=end,
                adjust=adj_param,
            )
        elif interval in ("weekly", "1w"):
            df = ak.stock_zh_a_hist(
                symbol=code, period="weekly",
                start_date=start, end_date=end,
                adjust=adj_param,
            )
        elif interval in ("monthly", "1mo"):
            df = ak.stock_zh_a_hist(
                symbol=code, period="monthly",
                start_date=start, end_date=end,
                adjust=adj_param,
            )
        else:
            # Minute bars: akshare returns intraday data for today only (free tier)
            logger.warning("Minute bars via akshare are limited; use tushare for history")
            df = ak.stock_zh_a_hist_min_em(symbol=code, period=interval, adjust=adj_param)

        return self._normalize_ashare(df)

    def _normalize_ashare(self, df: pd.DataFrame) -> pd.DataFrame:
        col_map = {
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna()

    # ── Futures ───────────────────────────────────────────────────────────────

    def _is_futures(self, symbol: str) -> bool:
        # Simple heuristic: futures symbols use uppercase letters without dot exchange suffix
        # e.g. "IF9999" (stock index main), "RB9999" (rebar main), "CU9999" (copper)
        return (
            symbol.upper() == symbol
            and "." not in symbol
            and any(symbol.startswith(p) for p in [
                "IF", "IC", "IH", "IM",          # stock index futures
                "RB", "HC", "I", "J", "JM",       # ferrous
                "CU", "AL", "ZN", "NI", "SN", "PB",  # non-ferrous
                "AU", "AG",                        # precious metals
                "SC", "FU", "BU",                  # energy
                "CF", "OI", "RM", "M", "Y", "P",  # ag oils
                "SR", "C", "CS", "A",              # grains
            ])
        )

    def _fetch_futures(self, ak, symbol: str, start: str, end: str) -> pd.DataFrame:
        """Fetch main-contract continuous futures and apply Panama rollover adjustment."""
        try:
            df = ak.futures_main_sina(symbol=symbol, adjust="")
        except Exception as e:
            logger.error(f"futures fetch failed for {symbol}: {e}")
            return pd.DataFrame()

        df = self._normalize_futures(df)
        df = self._panama_adjust(df)
        # Filter date range
        start_dt = pd.to_datetime(start, format="%Y%m%d")
        end_dt = pd.to_datetime(end, format="%Y%m%d")
        return df[(df.index >= start_dt) & (df.index <= end_dt)]

    def _normalize_futures(self, df: pd.DataFrame) -> pd.DataFrame:
        col_map = {
            "日期": "date", "开盘价": "open", "最高价": "high",
            "最低价": "low", "收盘价": "close", "成交量": "volume",
            "date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna()

    def _panama_adjust(self, df: pd.DataFrame) -> pd.DataFrame:
        """Panama continuous adjustment for futures rollover gaps.

        When the main contract switches, the price can jump sharply.
        We detect these jumps (> 3% of previous close) and apply a
        cumulative additive offset to earlier data so the series is
        continuous at the switch point.

        This preserves price levels near the current contract while
        making historical data comparable for technical analysis.
        """
        if len(df) < 2:
            return df

        df = df.copy()
        close = df["close"].values
        pct_changes = (close[1:] - close[:-1]) / close[:-1]

        # Threshold: jumps larger than 3% on the close (not OHLC limit check)
        ROLLOVER_THRESHOLD = 0.03
        rollover_indices = [i + 1 for i, p in enumerate(pct_changes) if abs(p) > ROLLOVER_THRESHOLD]

        if not rollover_indices:
            return df

        # Process right-to-left so each earlier section accumulates all
        # subsequent rollover gaps (forward Panama: historical data shifts UP
        # to match the newest contract's price level).
        for roll_idx in reversed(rollover_indices):
            current_close = df["close"].values          # re-read after each update
            gap = current_close[roll_idx] - current_close[roll_idx - 1]
            for col in ["open", "high", "low", "close"]:
                df.iloc[:roll_idx, df.columns.get_loc(col)] += gap

        return df


class CachedAkShareFeed:
    """AkShareFeed with SQLite caching and data validation."""

    def __init__(self, db: Optional[BarDatabase] = None) -> None:
        self._feed = AkShareFeed()
        self._db = db or BarDatabase()
        self._validator = DataValidator()

    def get_bars(
        self,
        symbol: str,
        interval: str = "daily",
        start: str = "2020-01-01",
        end: Optional[str] = None,
        adjust: str = "qfq",
        asset_type: str = "stock",
        force_refresh: bool = False,
    ) -> tuple[pd.DataFrame, ValidationReport]:
        end = end or datetime.today().strftime("%Y-%m-%d")

        if not force_refresh and self._db.has_data(symbol, interval, start, end):
            df = self._db.load(symbol, interval, start, end, adjust=adjust)
        else:
            # Incremental download: only fetch what's missing
            latest = self._db.latest_date(symbol, interval)
            fetch_start = latest or start
            df_new = self._feed.fetch_bars(symbol, interval, fetch_start, end, adjust)
            if not df_new.empty:
                self._db.upsert(symbol, interval, df_new, adjust)
            df = self._db.load(symbol, interval, start, end, adjust=adjust)

        report = self._validator.validate(df, symbol, asset_type)
        return df, report
