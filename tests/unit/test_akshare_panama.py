"""Tests for AkShareFeed — specifically the Panama rollover adjustment."""
import pytest
import pandas as pd
import numpy as np
from src.data.akshare_feed import AkShareFeed


@pytest.fixture
def feed():
    return AkShareFeed()


def _make_futures_df(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(prices), freq="B")
    df = pd.DataFrame({
        "open":   prices,
        "high":   [p + 5 for p in prices],
        "low":    [p - 5 for p in prices],
        "close":  prices,
        "volume": [10_000.0] * len(prices),
    }, index=dates)
    return df


class TestPanamaAdjust:
    def test_no_rollover_unchanged(self, feed):
        prices = [3000.0, 3010.0, 3020.0, 3015.0, 3025.0]
        df = _make_futures_df(prices)
        adj = feed._panama_adjust(df)
        assert list(adj["close"]) == pytest.approx(prices, rel=1e-6)

    def test_single_rollover_detected(self, feed):
        # Jump from 3000 → 3200 = 6.7% → rollover
        prices = [3000.0, 3010.0, 3020.0, 3200.0, 3210.0]
        df = _make_futures_df(prices)
        adj = feed._panama_adjust(df)
        # After adjustment, the jump should be smoothed out
        close = adj["close"].values
        pct_changes = abs((close[1:] - close[:-1]) / close[:-1])
        # The rollover jump should now be < 3%
        assert pct_changes[2] < 0.03, f"Rollover not smoothed: {pct_changes[2]:.2%}"

    def test_series_is_continuous_after_adjustment(self, feed):
        # Two rollovers
        prices = [3000.0, 3010.0, 3200.0, 3210.0, 3400.0, 3410.0]
        df = _make_futures_df(prices)
        adj = feed._panama_adjust(df)
        close = adj["close"].values
        pct_changes = abs((close[1:] - close[:-1]) / close[:-1])
        # All changes should be small (no rollover gap)
        assert all(p < 0.04 for p in pct_changes), f"Not all continuous: {pct_changes}"

    def test_empty_df_returns_empty(self, feed):
        result = feed._panama_adjust(pd.DataFrame())
        assert result.empty

    def test_single_row_returns_unchanged(self, feed):
        df = _make_futures_df([3000.0])
        adj = feed._panama_adjust(df)
        assert adj["close"].iloc[0] == pytest.approx(3000.0)

    def test_futures_symbol_detection(self, feed):
        assert feed._is_futures("IF9999")
        assert feed._is_futures("RB9999")
        assert feed._is_futures("CU2412")
        assert not feed._is_futures("000001.SZ")
        assert not feed._is_futures("BTC/USDT")
