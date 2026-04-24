"""Technical indicators wrapping the `ta` library.

All functions accept a pandas Series and return a Series of the same length
(NaN-padded at the start). This makes them drop-in compatible with backtest
DataFrames.

Optional ta-lib backend: if ta-lib C extension is available it will be used
for ATR and BBANDS (significantly faster on large datasets).
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def _use_talib() -> bool:
    try:
        import talib  # noqa: F401
        return True
    except ImportError:
        return False


# ── Trend ─────────────────────────────────────────────────────────────────────

def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ── Momentum ──────────────────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss
    result = 100 - (100 / (1 + rs))
    result[avg_loss == 0] = 100.0   # all gains → RSI = 100
    return result


def momentum(close: pd.Series, period: int = 10) -> pd.Series:
    """Rate-of-change momentum: (close / close[n] - 1) * 100."""
    return (close / close.shift(period) - 1) * 100


# ── Volatility ────────────────────────────────────────────────────────────────

def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    if _use_talib():
        import talib
        return pd.Series(
            talib.ATR(high.values, low.values, close.values, timeperiod=period),
            index=close.index,
        )
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, middle, lower)."""
    if _use_talib():
        import talib
        u, m, l = talib.BBANDS(close.values, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev)
        idx = close.index
        return pd.Series(u, index=idx), pd.Series(m, index=idx), pd.Series(l, index=idx)
    mid = sma(close, period)
    std = close.rolling(period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


# ── Volume ────────────────────────────────────────────────────────────────────

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).cumsum()


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    typical = (high + low + close) / 3
    return (typical * volume).cumsum() / volume.cumsum()
