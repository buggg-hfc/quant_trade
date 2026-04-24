"""Data quality validator.

Thresholds are loaded from settings.yaml validator_thresholds per asset type.
Never hardcode ±N% here — add to settings.yaml instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.utils.config import get_settings


@dataclass
class ValidationReport:
    symbol: str
    asset_type: str
    total_bars: int
    missing_bars: int = 0
    ohlc_errors: int = 0
    zero_volume_days: int = 0
    price_anomalies: list[str] = field(default_factory=list)
    gap_dates: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.missing_bars == 0
            and self.ohlc_errors == 0
            and len(self.price_anomalies) == 0
        )

    @property
    def badge(self) -> str:
        if self.ok and self.zero_volume_days == 0:
            return "green"
        if self.ohlc_errors > 0 or len(self.price_anomalies) > 3:
            return "red"
        return "yellow"

    def __str__(self) -> str:
        return (
            f"[{self.badge.upper()}] {self.symbol} ({self.asset_type}): "
            f"{self.total_bars} bars, {self.missing_bars} missing, "
            f"{self.ohlc_errors} OHLC errors, {len(self.price_anomalies)} anomalies, "
            f"{self.zero_volume_days} zero-vol days"
        )


class DataValidator:
    """Validate an OHLCV DataFrame.

    asset_type must be one of the keys in settings.yaml validator_thresholds:
      stock, futures_commodity, futures_index, futures_energy, crypto
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._thresholds: dict[str, float] = cfg.validator_thresholds

    def validate(
        self,
        df: pd.DataFrame,
        symbol: str,
        asset_type: str = "stock",
    ) -> ValidationReport:
        limit = self._thresholds.get(asset_type, self._thresholds.get("stock", 0.11))
        report = ValidationReport(
            symbol=symbol,
            asset_type=asset_type,
            total_bars=len(df),
        )
        if df.empty:
            return report

        # 1. Missing values
        report.missing_bars = int(df[["open", "high", "low", "close", "volume"]].isna().any(axis=1).sum())

        # 2. OHLC consistency
        df = df.dropna(subset=["open", "high", "low", "close"])
        bad = (
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        )
        report.ohlc_errors = int(bad.sum())

        # 3. Price anomalies: single-bar change > limit
        pct = df["close"].pct_change().abs()
        bad_pct = pct[pct > limit]
        report.price_anomalies = [str(d)[:10] for d in bad_pct.index.tolist()]

        # 4. Zero volume
        if "volume" in df.columns:
            report.zero_volume_days = int((df["volume"] == 0).sum())

        # 5. Calendar gaps (trading-day continuity) — approximate via date diff
        if hasattr(df.index, "to_series"):
            dates = pd.to_datetime(df.index).to_series().reset_index(drop=True)
            diffs = dates.diff().dt.days.dropna()
            # Flag gaps > 5 trading days (accounts for holidays/weekends)
            gap_mask = diffs > 7
            report.gap_dates = [str(dates.iloc[i])[:10] for i in gap_mask[gap_mask].index.tolist()]

        return report
