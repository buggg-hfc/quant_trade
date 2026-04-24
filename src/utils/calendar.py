from __future__ import annotations

from datetime import date, datetime, time, timezone


class TradingCalendar:
    """Trading session definitions for each asset class."""

    # A-share: Mon-Fri, two sessions
    ASHARE_SESSIONS = [
        (time(9, 30), time(11, 30)),
        (time(13, 0), time(15, 0)),
    ]
    # Futures: Mon-Fri with night session (simplified, exchange-specific details omitted)
    FUTURES_DAY_SESSIONS = [
        (time(9, 0), time(11, 30)),
        (time(13, 30), time(15, 0)),
    ]

    @staticmethod
    def is_crypto_trading(dt: datetime) -> bool:
        """Crypto markets are 24×365."""
        return True

    @staticmethod
    def is_ashare_trading(dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        for start, end in TradingCalendar.ASHARE_SESSIONS:
            if start <= t <= end:
                return True
        return False

    @staticmethod
    def is_futures_day_trading(dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        for start, end in TradingCalendar.FUTURES_DAY_SESSIONS:
            if start <= t <= end:
                return True
        return False
