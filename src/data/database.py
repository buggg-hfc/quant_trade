"""SQLite cache layer for OHLCV bar data.

Schema: one table per (symbol, interval). Supports incremental updates
(only insert rows newer than the latest cached date).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.utils.helpers import data_cache_dir


class BarDatabase:
    """Thread-safe SQLite wrapper for bar data caching."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        path = db_path or str(data_cache_dir() / "bar_cache.db")
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    # ── Table management ──────────────────────────────────────────────────────

    def _table(self, symbol: str, interval: str) -> str:
        safe = symbol.replace(".", "_").replace("/", "_").replace("-", "_")
        return f"bar_{safe}_{interval}"

    def _ensure_table(self, table: str) -> None:
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                date        TEXT PRIMARY KEY,
                open        REAL NOT NULL,
                high        REAL NOT NULL,
                low         REAL NOT NULL,
                close       REAL NOT NULL,
                volume      REAL NOT NULL,
                adjust      TEXT DEFAULT ''
            )
        """)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(self, symbol: str, interval: str, df: pd.DataFrame, adjust: str = "qfq") -> int:
        """Insert or replace rows. Returns number of rows written."""
        if df.empty:
            return 0
        table = self._table(symbol, interval)
        self._ensure_table(table)
        df = df.copy()
        df["adjust"] = adjust
        # Normalise date column to ISO string
        if "date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        rows = df[["date", "open", "high", "low", "close", "volume", "adjust"]].values.tolist()
        self._conn.executemany(
            f"INSERT OR REPLACE INTO {table} (date,open,high,low,close,volume,adjust) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    # ── Read ──────────────────────────────────────────────────────────────────

    def load(
        self,
        symbol: str,
        interval: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load cached bars. Returns empty DataFrame if not cached."""
        table = self._table(symbol, interval)
        try:
            conds = []
            params: list = []
            if start:
                conds.append("date >= ?"); params.append(start)
            if end:
                conds.append("date <= ?"); params.append(end)
            if adjust is not None:
                conds.append("adjust = ?"); params.append(adjust)
            where = ("WHERE " + " AND ".join(conds)) if conds else ""
            df = pd.read_sql(
                f"SELECT * FROM {table} {where} ORDER BY date",
                self._conn, params=params, parse_dates=["date"], index_col="date",
            )
            return df
        except Exception:
            return pd.DataFrame()

    def latest_date(self, symbol: str, interval: str) -> Optional[str]:
        """Return the most recent cached date string, or None if not cached."""
        table = self._table(symbol, interval)
        try:
            row = self._conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None

    def has_data(self, symbol: str, interval: str, start: str, end: str) -> bool:
        """Quick check: does the cache span the full requested range?"""
        first_date = None
        table = self._table(symbol, interval)
        try:
            row = self._conn.execute(f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
            if row and row[0] and row[1]:
                return row[0] <= start and row[1] >= end
        except Exception:
            pass
        return False

    def list_symbols(self) -> list[str]:
        """Return all cached symbol+interval combos."""
        cur = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bar_%'")
        return [r[0] for r in cur.fetchall()]

    def drop(self, symbol: str, interval: str) -> None:
        table = self._table(symbol, interval)
        self._conn.execute(f"DROP TABLE IF EXISTS {table}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
