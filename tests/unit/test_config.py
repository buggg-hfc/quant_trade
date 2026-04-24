"""Tests for configuration management."""
import pytest
import yaml
from pathlib import Path
from src.utils.config import Settings, get_settings, reload_settings


@pytest.fixture(autouse=True)
def clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestSettings:
    def test_default_settings(self):
        s = Settings()
        assert s.backtest.initial_capital == 1_000_000.0
        assert s.backtest.commission_rate == 0.0003
        assert s.risk.max_position_pct == 0.20
        assert s.data.adjust == "qfq"

    def test_validator_thresholds_present(self):
        s = Settings()
        assert "stock" in s.validator_thresholds
        assert "futures_commodity" in s.validator_thresholds
        assert "crypto" in s.validator_thresholds
        assert s.validator_thresholds["stock"] == pytest.approx(0.11)
        assert s.validator_thresholds["crypto"] == pytest.approx(1.0)

    def test_load_from_yaml(self, tmp_path):
        cfg = {
            "backtest": {"initial_capital": 500_000, "commission_rate": 0.0005},
            "system": {"log_level": "DEBUG"},
            "validator_thresholds": {"stock": 0.20, "crypto": 0.5},
        }
        p = tmp_path / "settings.yaml"
        p.write_text(yaml.dump(cfg))
        s = get_settings(str(p))
        assert s.backtest.initial_capital == 500_000
        assert s.backtest.commission_rate == pytest.approx(0.0005)
        assert s.system.log_level == "DEBUG"
        assert s.validator_thresholds["stock"] == pytest.approx(0.20)

    def test_partial_yaml_uses_defaults(self, tmp_path):
        cfg = {"system": {"mode": "live"}}
        p = tmp_path / "settings.yaml"
        p.write_text(yaml.dump(cfg))
        s = get_settings(str(p))
        assert s.system.mode == "live"
        assert s.backtest.initial_capital == 1_000_000.0  # default

    def test_missing_yaml_returns_defaults(self):
        s = get_settings("/nonexistent/path.yaml")
        assert s.backtest.initial_capital == 1_000_000.0
