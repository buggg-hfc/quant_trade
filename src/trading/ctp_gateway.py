"""CTPGateway: domestic futures live trading via openctp-ctp.

Prerequisites:
  pip install openctp-ctp
  CTP broker account + simulated environment (SimNow) or live broker.
  Credentials stored via KeyStore — never in settings.yaml.

Usage:
    from src.utils.keystore import KeyStore
    from src.trading.ctp_gateway import CTPGateway

    password = KeyStore().get_key("ctp_password", master_pwd)
    gw = CTPGateway()
    gw.on_trade(my_trade_handler)
    gw.connect(password=password)
    gw.subscribe(["IF2412", "RB2501"])
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Optional

from src.core.object import (
    OrderData, TradeData, TickData, BarData, AccountData, PositionData,
)
from src.trading.base_gateway import BaseGateway, OrderRequest
from src.utils.config import get_settings

logger = logging.getLogger(__name__)


class CTPGateway(BaseGateway):
    """Futures live gateway wrapping openctp-ctp Python API."""

    def __init__(self) -> None:
        super().__init__("ctp")
        cfg = get_settings().gateway.ctp
        self._broker_id  = cfg.broker_id
        self._user_id    = cfg.user_id
        self._td_address = cfg.td_address
        self._md_address = cfg.md_address
        self._password: Optional[str] = None
        self._td_api = None
        self._md_api = None
        self._connected = False
        self._req_id: int = 0
        self._lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, password: Optional[str] = None) -> None:
        try:
            import openctp_ctp as ctp  # type: ignore
        except ImportError:
            raise ImportError("openctp-ctp not installed. Run: pip install openctp-ctp")

        self._password = password
        self._td_api = ctp.CThostFtdcTraderApi.CreateFtdcTraderApi()
        self._md_api = ctp.CThostFtdcMdApi.CreateFtdcMdApi()

        # Register SPI callbacks (simplified — production code uses full SPI subclass)
        self._td_api.RegisterFront(self._td_address)
        self._td_api.Init()
        logger.info(f"CTPGateway connecting to {self._td_address}")

    def disconnect(self) -> None:
        if self._td_api:
            self._td_api.Release()
        if self._md_api:
            self._md_api.Release()
        self._connected = False
        logger.info("CTPGateway disconnected")

    def subscribe(self, symbols: list[str]) -> None:
        if self._md_api:
            self._md_api.SubscribeMarketData(symbols)

    def send_order(self, req: OrderRequest) -> str:
        if not self._connected:
            raise RuntimeError("CTPGateway not connected")
        import openctp_ctp as ctp  # type: ignore

        with self._lock:
            self._req_id += 1
            rid = self._req_id

        field = ctp.CThostFtdcInputOrderField()
        field.BrokerID          = self._broker_id
        field.InvestorID        = self._user_id
        field.InstrumentID      = req.symbol
        field.Direction         = "0" if req.direction == "LONG" else "1"
        field.CombOffsetFlag    = "0"   # open; "1" = close
        field.LimitPrice        = req.price
        field.VolumeTotalOriginal = int(req.volume)
        field.TimeCondition     = "3"   # GFD
        field.VolumeCondition   = "1"   # any volume
        field.OrderPriceType    = "2" if req.order_type == "LIMIT" else "1"

        self._td_api.ReqOrderInsert(field, rid)
        oid = f"ctp_{rid}"
        req.order_id = oid
        order = OrderData(
            order_id=oid, symbol=req.symbol, direction=req.direction,
            order_type=req.order_type, price=req.price, volume=req.volume,
            status="SUBMITTED",
        )
        self.order_book.add(order)
        return oid

    def cancel_order(self, order_id: str) -> None:
        if not self._connected or not self._td_api:
            return
        import openctp_ctp as ctp  # type: ignore
        with self._lock:
            self._req_id += 1
            rid = self._req_id
        field = ctp.CThostFtdcInputOrderActionField()
        field.BrokerID   = self._broker_id
        field.InvestorID = self._user_id
        field.ActionFlag = "0"   # delete
        self._td_api.ReqOrderAction(field, rid)

    def query_account(self) -> AccountData:
        # In production this would be async; here returns a stub
        return AccountData(balance=0.0, available=0.0)

    def query_position(self, symbol: str) -> PositionData:
        return PositionData(symbol=symbol)
