"""Tests for TradingCalendar."""
import pytest
from datetime import datetime, date
from src.utils.calendar import TradingCalendar


class TestTradingCalendar:
    def test_ashare_open_morning(self):
        dt = datetime(2024, 3, 15, 9, 45)  # Friday 09:45
        assert TradingCalendar.is_ashare_trading(dt)

    def test_ashare_open_afternoon(self):
        dt = datetime(2024, 3, 15, 14, 0)  # Friday 14:00
        assert TradingCalendar.is_ashare_trading(dt)

    def test_ashare_closed_lunch(self):
        dt = datetime(2024, 3, 15, 12, 0)  # Friday 12:00 — lunch
        assert not TradingCalendar.is_ashare_trading(dt)

    def test_ashare_closed_weekend(self):
        dt = datetime(2024, 3, 16, 10, 0)  # Saturday
        assert not TradingCalendar.is_ashare_trading(dt)

    def test_ashare_closed_before_open(self):
        dt = datetime(2024, 3, 15, 9, 0)  # Friday 09:00
        assert not TradingCalendar.is_ashare_trading(dt)

    def test_crypto_always_trading(self):
        for dt in [
            datetime(2024, 1, 1, 0, 0),   # New Year midnight
            datetime(2024, 12, 25, 12, 0), # Christmas
        ]:
            assert TradingCalendar.is_crypto_trading(dt)

    def test_trading_dates_excludes_weekends(self):
        dates = TradingCalendar.trading_dates_in_range(date(2024, 3, 11), date(2024, 3, 15))
        weekdays = [d.weekday() for d in dates]
        assert all(w < 5 for w in weekdays)
        assert len(dates) == 5  # Mon-Fri

    def test_next_trading_day_skips_weekend(self):
        friday = date(2024, 3, 15)
        next_d = TradingCalendar.next_trading_day(friday)
        assert next_d == date(2024, 3, 18)  # Monday

    def test_next_trading_day_weekday(self):
        monday = date(2024, 3, 11)
        next_d = TradingCalendar.next_trading_day(monday)
        assert next_d == date(2024, 3, 12)  # Tuesday
