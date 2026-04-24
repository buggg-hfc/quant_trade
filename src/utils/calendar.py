"""Trading calendar utilities for A-share, futures, and crypto markets."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional


class TradingCalendar:
    """Session definitions per asset class."""

    A_SHARE_SESSIONS = [
        (time(9, 30), time(11, 30)),
        (time(13, 0), time(15, 0)),
    ]
    FUTURES_DAY_SESSIONS = [
        (time(9, 0), time(11, 30)),
        (time(13, 30), time(15, 0)),
    ]
    FUTURES_NIGHT_SESSIONS = [
        # Simplified: many commodities have night sessions; exact hours vary by exchange
        (time(21, 0), time(23, 59)),
    ]

    @staticmethod
    def is_crypto_trading(_dt: Optional[datetime] = None) -> bool:
        return True  # 24×365

    @staticmethod
    def is_ashare_trading(dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        return any(start <= t <= end for start, end in TradingCalendar.A_SHARE_SESSIONS)

    @staticmethod
    def is_futures_day_trading(dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        return any(start <= t <= end for start, end in TradingCalendar.FUTURES_DAY_SESSIONS)

    @staticmethod
    def is_futures_night_trading(dt: datetime) -> bool:
        # Friday night → Saturday morning: no night session
        if dt.weekday() == 4 and dt.time() >= time(21, 0):
            return False
        if dt.weekday() == 5:
            return False
        t = dt.time()
        return any(start <= t for start, end in TradingCalendar.FUTURES_NIGHT_SESSIONS)

    @staticmethod
    def trading_dates_in_range(start: date, end: date, skip_weekends: bool = True) -> list[date]:
        """Return all (approximate) trading dates between start and end inclusive."""
        dates = []
        current = start
        while current <= end:
            if not skip_weekends or current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        return dates

    @staticmethod
    def next_trading_day(dt: date, skip_weekends: bool = True) -> date:
        next_d = dt + timedelta(days=1)
        while skip_weekends and next_d.weekday() >= 5:
            next_d += timedelta(days=1)
        return next_d
