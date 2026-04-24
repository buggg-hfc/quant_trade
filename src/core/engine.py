from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.base import BaseStrategy


class MainEngine:
    """Top-level engine: wires EventEngine, Gateway, RiskManager, and strategies."""

    def __init__(self, gateway: str = "paper", exchange: str = "binance",
                 sandbox: bool = True) -> None:
        from quant_core import EventEngine
        self.event_engine = EventEngine()
        self.gateway_name = gateway
        self.exchange = exchange
        self.sandbox = sandbox
        self.strategies: list[BaseStrategy] = []
        self._gateway = None

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self.strategies.append(strategy)

    def start(self) -> None:
        self._gateway = self._build_gateway()
        self.event_engine.start()
        self._gateway.connect()
        for strategy in self.strategies:
            strategy.init()
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._gateway:
            self._gateway.disconnect()
        self.event_engine.stop()

    def _build_gateway(self):
        if self.gateway_name == "paper":
            from src.trading.paper_gateway import PaperGateway
            return PaperGateway()
        elif self.gateway_name == "ctp":
            from src.trading.ctp_gateway import CTPGateway
            return CTPGateway()
        elif self.gateway_name == "crypto":
            from src.trading.crypto_gateway import CryptoGateway
            return CryptoGateway(exchange_id=self.exchange, sandbox=self.sandbox)
        else:
            raise ValueError(f"Unknown gateway: {self.gateway_name}")
