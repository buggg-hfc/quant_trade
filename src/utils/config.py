"""Configuration management: settings.yaml + .env → typed Settings object.

Usage:
    from src.utils.config import get_settings
    cfg = get_settings()
    print(cfg.backtest.initial_capital)
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).parent.parent.parent  # project root


# ── Sub-models ────────────────────────────────────────────────────────────────

class SystemConfig(BaseModel):
    mode: str = "backtest"
    log_level: str = "INFO"


class DataConfig(BaseModel):
    default_source: str = "akshare"
    adjust: str = "qfq"


class BacktestConfig(BaseModel):
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage: float = 0.001
    price_limit_pct: float = 0.10


class RiskConfig(BaseModel):
    max_position_pct: float = 0.20
    daily_loss_limit: float = 0.02
    max_drawdown: float = 0.10
    max_order_volume: float = 1000.0


class CtpGatewayConfig(BaseModel):
    broker_id: str = ""
    user_id: str = ""
    td_address: str = ""
    md_address: str = ""


class XtpGatewayConfig(BaseModel):
    server_ip: str = ""
    server_port: int = 24800
    account: str = ""
    client_id: int = 1


class CryptoGatewayConfig(BaseModel):
    exchange: str = "binance"
    sandbox: bool = True


class GatewayConfig(BaseModel):
    ctp: CtpGatewayConfig = Field(default_factory=CtpGatewayConfig)
    xtp: XtpGatewayConfig = Field(default_factory=XtpGatewayConfig)
    crypto: CryptoGatewayConfig = Field(default_factory=CryptoGatewayConfig)


class EmailNotifierConfig(BaseModel):
    smtp_host: str = "smtp.qq.com"
    port: int = 465
    sender: str = ""
    receiver: str = ""


class NotifierConfig(BaseModel):
    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)
    wechat_webhook: str = ""


class ValidatorThresholds(BaseModel):
    stock: float = 0.11
    futures_commodity: float = 0.06
    futures_index: float = 0.11
    futures_energy: float = 0.16
    crypto: float = 1.0


# ── Root settings ─────────────────────────────────────────────────────────────

class Settings(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    notifier: NotifierConfig = Field(default_factory=NotifierConfig)
    validator_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "stock": 0.11,
            "futures_commodity": 0.06,
            "futures_index": 0.11,
            "futures_energy": 0.16,
            "crypto": 1.0,
        }
    )


@functools.lru_cache(maxsize=1)
def get_settings(yaml_path: Optional[str] = None) -> Settings:
    path = Path(yaml_path) if yaml_path else _ROOT / "config" / "settings.yaml"
    if not path.exists():
        return Settings()
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return Settings(**raw)


def reload_settings() -> Settings:
    """Force reload (clears lru_cache). Useful after config file changes."""
    get_settings.cache_clear()
    return get_settings()
