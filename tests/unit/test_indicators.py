"""Tests for technical indicators."""
import pytest
import pandas as pd
import numpy as np
from src.strategy.indicators import sma, ema, rsi, macd, atr, bollinger_bands, momentum


def _series(vals) -> pd.Series:
    return pd.Series(vals, dtype=float)


class TestSMA:
    def test_trailing_average(self):
        s = _series([1, 2, 3, 4, 5])
        result = sma(s, 3)
        assert result.iloc[4] == pytest.approx(4.0)

    def test_leading_nan(self):
        result = sma(_series([1, 2, 3, 4, 5]), 3)
        assert result.iloc[0] != result.iloc[0]   # NaN

    def test_period_1_identity(self):
        vals = [10.0, 20.0, 30.0]
        result = sma(_series(vals), 1)
        assert list(result) == pytest.approx(vals)


class TestEMA:
    def test_ema_weights_recent_more(self):
        # After a sharp rise, EMA should be closer to recent price than SMA
        vals = [100.0] * 10 + [200.0]
        close = _series(vals)
        e = ema(close, 10)
        s = sma(close, 10)
        assert e.iloc[-1] > s.iloc[-1]

    def test_ema_length_preserved(self):
        close = _series(range(20))
        assert len(ema(close, 5)) == 20


class TestRSI:
    def test_all_up_gives_high_rsi(self):
        close = _series([100.0 + i for i in range(20)])
        r = rsi(close, 14)
        assert r.dropna().iloc[-1] > 70

    def test_all_down_gives_low_rsi(self):
        close = _series([200.0 - i for i in range(20)])
        r = rsi(close, 14)
        assert r.dropna().iloc[-1] < 30

    def test_rsi_bounds(self):
        import random
        random.seed(42)
        close = _series([100 + random.gauss(0, 5) for _ in range(100)])
        r = rsi(close, 14).dropna()
        assert (r >= 0).all() and (r <= 100).all()


class TestMACD:
    def test_returns_three_series(self):
        close = _series([100.0 + i * 0.5 for i in range(50)])
        ml, sl, hist = macd(close)
        assert len(ml) == len(sl) == len(hist) == 50

    def test_histogram_is_macd_minus_signal(self):
        close = _series([100.0 + i * 0.5 for i in range(50)])
        ml, sl, hist = macd(close)
        diff = (ml - sl - hist).dropna()
        assert diff.abs().max() < 1e-10


class TestATR:
    def test_higher_volatility_higher_atr(self):
        n = 30
        hi_vol_high  = _series([105.0 + i for i in range(n)])
        hi_vol_low   = _series([95.0  + i for i in range(n)])
        lo_vol_high  = _series([101.0 + i for i in range(n)])
        lo_vol_low   = _series([99.0  + i for i in range(n)])
        close        = _series([100.0 + i for i in range(n)])
        hi = atr(hi_vol_high, hi_vol_low, close, 14).dropna().iloc[-1]
        lo = atr(lo_vol_high, lo_vol_low, close, 14).dropna().iloc[-1]
        assert hi > lo


class TestBollingerBands:
    def test_price_mostly_inside_bands(self):
        np.random.seed(0)
        close = _series(100 + np.random.randn(100).cumsum())
        upper, mid, lower = bollinger_bands(close, 20, 2.0)
        valid = upper.notna()
        inside = ((close[valid] >= lower[valid]) & (close[valid] <= upper[valid])).sum()
        assert inside / valid.sum() > 0.85   # ~95% theoretical, some edge variance

    def test_upper_above_lower(self):
        close = _series([100.0 + i * 0.1 for i in range(50)])
        upper, _, lower = bollinger_bands(close, 10)
        assert (upper.dropna() >= lower.dropna()).all()


class TestMomentum:
    def test_positive_trend_positive_momentum(self):
        close = _series([100.0 + i for i in range(20)])
        m = momentum(close, 10)
        assert m.dropna().iloc[-1] > 0

    def test_flat_gives_zero_momentum(self):
        close = _series([100.0] * 20)
        m = momentum(close, 10)
        assert m.dropna().iloc[-1] == pytest.approx(0.0)
