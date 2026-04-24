"""Tests for BarDatabase SQLite cache layer."""
import pytest
import pandas as pd
from src.data.database import BarDatabase


@pytest.fixture
def db(tmp_path):
    return BarDatabase(str(tmp_path / "test.db"))


def sample_df(start="2024-01-02", periods=5, base=10.0) -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=periods, freq="B")
    return pd.DataFrame({
        "date": dates,
        "open":   [base + i * 0.1 for i in range(periods)],
        "high":   [base + i * 0.1 + 0.5 for i in range(periods)],
        "low":    [base + i * 0.1 - 0.3 for i in range(periods)],
        "close":  [base + i * 0.1 + 0.2 for i in range(periods)],
        "volume": [1_000_000.0] * periods,
    })


class TestBarDatabase:
    def test_upsert_and_load(self, db):
        df = sample_df()
        n = db.upsert("000001.SZ", "daily", df, adjust="qfq")
        assert n == 5
        result = db.load("000001.SZ", "daily")
        assert len(result) == 5
        assert list(result.columns) == ["open", "high", "low", "close", "volume", "adjust"]

    def test_upsert_idempotent(self, db):
        df = sample_df()
        db.upsert("000001.SZ", "daily", df)
        db.upsert("000001.SZ", "daily", df)  # second upsert should not duplicate
        result = db.load("000001.SZ", "daily")
        assert len(result) == 5

    def test_load_date_filter(self, db):
        db.upsert("000001.SZ", "daily", sample_df(periods=10))
        result = db.load("000001.SZ", "daily", start="2024-01-02", end="2024-01-05")
        assert len(result) <= 4

    def test_latest_date_none_when_empty(self, db):
        assert db.latest_date("MISSING", "daily") is None

    def test_latest_date_after_insert(self, db):
        db.upsert("BTC/USDT", "1d", sample_df("2024-01-02", 3))
        latest = db.latest_date("BTC/USDT", "1d")
        assert latest is not None
        assert latest >= "2024-01-02"

    def test_has_data_false_when_empty(self, db):
        assert not db.has_data("X", "daily", "2024-01-01", "2024-12-31")

    def test_has_data_true_after_insert(self, db):
        db.upsert("000002.SZ", "daily", sample_df("2024-01-02", 5))
        assert db.has_data("000002.SZ", "daily", "2024-01-02", "2024-01-02")

    def test_different_symbols_independent(self, db):
        db.upsert("SYM_A", "daily", sample_df(periods=3))
        db.upsert("SYM_B", "daily", sample_df(periods=7, base=50.0))
        assert len(db.load("SYM_A", "daily")) == 3
        assert len(db.load("SYM_B", "daily")) == 7

    def test_drop_table(self, db):
        db.upsert("TEMP", "daily", sample_df())
        db.drop("TEMP", "daily")
        result = db.load("TEMP", "daily")
        assert result.empty

    def test_list_symbols(self, db):
        db.upsert("AAA", "daily", sample_df())
        db.upsert("BBB", "1d", sample_df())
        tables = db.list_symbols()
        assert any("AAA" in t for t in tables)
        assert any("BBB" in t for t in tables)
