"""Tushare Pro data feed (paid, optional).

Requires a Tushare token stored via KeyStore:
    from src.utils.keystore import KeyStore
    ks = KeyStore("data_cache/keystore.db")
    ks.set_key("tushare_token", "<your_token>", master_pwd="<your_pwd>")

Then configure in GUI or env:
    TUSHARE_TOKEN=<token>  # fallback for development
"""
from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from src.data.base import BaseDataFeed


class TushareFeed(BaseDataFeed):
    """Daily/minute bars and financial data via Tushare Pro."""

    def name(self) -> str:
        return "tushare"

    def _get_api(self):
        try:
            import tushare as ts
        except ImportError:
            raise ImportError("tushare not installed. Run: pip install tushare")

        token = os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            raise RuntimeError(
                "Tushare token not configured. "
                "Set TUSHARE_TOKEN env var or use KeyStore.set_key('tushare_token', ...)"
            )
        ts.set_token(token)
        return ts.pro_api()

    def fetch_bars(
        self,
        symbol: str,
        interval: str = "daily",
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        pro = self._get_api()
        # Tushare uses ts_code format: "000001.SZ"
        ts_code = symbol if "." in symbol else f"{symbol}.SZ"
        start_ts = (start or "2015-01-01").replace("-", "")
        end_ts = (end or "").replace("-", "") or None

        adj_map = {"qfq": "qfq", "hfq": "hfq", "": None}
        adj_factor = adj_map.get(adjust, "qfq")

        if interval in ("daily", "1d"):
            df = pro.daily(ts_code=ts_code, start_date=start_ts, end_date=end_ts)
            if adj_factor:
                # Apply adjustment factor
                adj = pro.adj_factor(ts_code=ts_code, start_date=start_ts, end_date=end_ts)
                df = self._apply_adjust(df, adj, adj_factor)
        else:
            # Minute bars (requires higher-tier token)
            freq_map = {"1min": "1min", "5min": "5min", "15min": "15min",
                        "30min": "30min", "60min": "60min"}
            freq = freq_map.get(interval, "1min")
            df = pro.stk_mins(ts_code=ts_code, freq=freq, start_date=start_ts)

        return self._normalize(df)

    def _apply_adjust(self, df: pd.DataFrame, adj: pd.DataFrame, mode: str) -> pd.DataFrame:
        if adj.empty:
            return df
        df = df.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
        df["adj_factor"] = df["adj_factor"].fillna(1.0)
        if mode == "qfq":
            latest_factor = df["adj_factor"].iloc[0]
            rel = df["adj_factor"] / latest_factor
        else:  # hfq
            rel = df["adj_factor"]
        for col in ["open", "high", "low", "close"]:
            df[col] = (df[col] * rel).round(3)
        return df

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        col_map = {"trade_date": "date", "vol": "volume"}
        df = df.rename(columns=col_map)
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df["date"] = pd.to_datetime(df["date"].astype(str))
        df = df.set_index("date").sort_index()
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna()
