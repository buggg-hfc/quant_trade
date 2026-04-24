"""Tests for DataValidator."""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# Mock settings before importing DataValidator
_MOCK_SETTINGS = MagicMock()
_MOCK_SETTINGS.validator_thresholds = {
    "stock": 0.11,
    "futures_commodity": 0.06,
    "futures_index": 0.11,
    "futures_energy": 0.16,
    "crypto": 1.0,
}

with patch("src.utils.config.get_settings", return_value=_MOCK_SETTINGS):
    from src.data.data_validator import DataValidator, ValidationReport


@pytest.fixture
def validator():
    with patch("src.data.data_validator.get_settings", return_value=_MOCK_SETTINGS):
        return DataValidator()


def clean_df(n=10, base=10.0) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    df = pd.DataFrame({
        "open":   [base + 0.1 * i for i in range(n)],
        "high":   [base + 0.1 * i + 0.5 for i in range(n)],
        "low":    [base + 0.1 * i - 0.3 for i in range(n)],
        "close":  [base + 0.1 * i + 0.2 for i in range(n)],
        "volume": [100_000.0] * n,
    }, index=dates)
    return df


class TestDataValidator:
    def test_clean_data_is_green(self, validator):
        r = validator.validate(clean_df(), "000001.SZ", "stock")
        assert r.badge == "green"
        assert r.ok

    def test_missing_values_detected(self, validator):
        df = clean_df()
        df.iloc[3, df.columns.get_loc("close")] = np.nan
        r = validator.validate(df, "000001.SZ", "stock")
        assert r.missing_bars >= 1

    def test_ohlc_error_detected(self, validator):
        df = clean_df()
        # high < low → OHLC error
        df.iloc[2, df.columns.get_loc("high")] = df.iloc[2]["low"] - 1.0
        r = validator.validate(df, "000001.SZ", "stock")
        assert r.ohlc_errors >= 1

    def test_price_anomaly_detected_stock(self, validator):
        df = clean_df()
        # +20% jump → exceeds stock threshold of 11%
        df.iloc[5, df.columns.get_loc("close")] *= 1.20
        r = validator.validate(df, "000001.SZ", "stock")
        assert len(r.price_anomalies) >= 1
        assert r.badge != "green"

    def test_futures_commodity_threshold(self, validator):
        df = clean_df()
        # +7% jump: exceeds commodity (6%) but would pass stock (11%)
        df.iloc[5, df.columns.get_loc("close")] *= 1.07
        r_future = validator.validate(df, "RB9999", "futures_commodity")
        r_stock = validator.validate(df, "000001.SZ", "stock")
        assert len(r_future.price_anomalies) >= 1  # detected as anomaly
        assert len(r_stock.price_anomalies) == 0   # within stock limit

    def test_zero_volume_days(self, validator):
        df = clean_df()
        df.iloc[4, df.columns.get_loc("volume")] = 0.0
        r = validator.validate(df, "000001.SZ", "stock")
        assert r.zero_volume_days == 1

    def test_empty_dataframe(self, validator):
        r = validator.validate(pd.DataFrame(), "000001.SZ", "stock")
        assert r.total_bars == 0
        assert r.ok

    def test_report_str(self, validator):
        r = validator.validate(clean_df(), "TEST", "stock")
        s = str(r)
        assert "TEST" in s
        assert "green" in s.lower() or "GREEN" in s

    def test_crypto_threshold_permissive(self, validator):
        df = clean_df()
        # +50% jump: should be fine for crypto (threshold=1.0 = 100%)
        df.iloc[5, df.columns.get_loc("close")] *= 1.50
        r = validator.validate(df, "BTC/USDT", "crypto")
        assert len(r.price_anomalies) == 0
