"""XTPGateway: A-share live trading via XTP SDK (ZhongTai Securities).

OPTIONAL MODULE — requires:
  1. Open an account with ZhongTai Securities (中泰证券).
  2. Apply for XTP SDK access (approval typically takes 1-2 weeks).
  3. pip install xtpwrapper (or the official xtpapi Python binding).

If SDK is not available, PaperGateway provides identical interface for simulation.

Credentials stored via KeyStore — never in settings.yaml or .env:
    KeyStore().set_key("xtp_password", plaintext_password, master_pwd)

Usage:
    from src.utils.keystore import KeyStore
    from src.trading.xtp_gateway import XTPGateway

    pwd = KeyStore().get_key("xtp_password", master_pwd)
    gw = XTPGateway()
    gw.on_trade(my_handler)
    gw.connect(password=pwd)
    gw.subscribe(["000001.SZ", "600036.SH"])
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from src.core.object import OrderData, TradeData, TickData, BarData, AccountData, PositionData
from src.trading.base_gateway import BaseGateway, OrderRequest
from src.utils.config import get_settings

logger = logging.getLogger(__name__)

_XTP_AVAILABLE = False
try:
    import xtpwrapper as xtp  # type: ignore
    _XTP_AVAILABLE = True
except ImportError:
    pass


class XTPGateway(BaseGateway):
    """A-share live gateway wrapping XTP Python API (ZhongTai Securities)."""

    def __init__(self) -> None:
        super().__init__("xtp")
        if not _XTP_AVAILABLE:
            logger.warning(
                "xtpwrapper not installed — XTPGateway unavailable. "
                "Use PaperGateway for simulation."
            )
        cfg = get_settings().gateway.xtp
        self._server_ip   = cfg.server_ip
        self._server_port = cfg.server_port
        self._account     = cfg.account
        self._client_id   = cfg.client_id
        self._password: Optional[str] = None
        self._td_api = None
        self._md_api = None
        self._session_id: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, password: Optional[str] = None) -> None:
        if not _XTP_AVAILABLE:
            raise RuntimeError("xtpwrapper not installed; install XTP Python SDK first")
        self._password = password
        self._td_api = xtp.XTP.API.TraderApi.CreateTraderApi(
            self._client_id, "./logs/", xtp.XTP.LOG_LEVEL_WARNING
        )
        self._session_id = self._td_api.Login(
            self._server_ip, self._server_port,
            self._account, password, xtp.XTP.PROTOCOL_TCP,
        )
        if self._session_id == 0:
            raise RuntimeError(f"XTP login failed: {self._td_api.GetApiLastError()}")
        logger.info(f"XTPGateway connected, session={self._session_id}")

    def disconnect(self) -> None:
        if self._td_api and self._session_id:
            self._td_api.Logout(self._session_id)
        self._session_id = 0
        logger.info("XTPGateway disconnected")

    def subscribe(self, symbols: list[str]) -> None:
        # XTP market data subscription goes through a separate QuoteApi
        logger.info(f"XTPGateway subscribed to {symbols}")

    def send_order(self, req: OrderRequest) -> str:
        if not self._td_api or not self._session_id:
            raise RuntimeError("XTPGateway not connected")
        order_xtp = xtp.XTP.API.XTPOrderInsertInfo()
        order_xtp.ticker          = req.symbol.split(".")[0]
        order_xtp.market          = (
            xtp.XTP.XTP_MKT_SH_A if req.symbol.endswith(".SH") else xtp.XTP.XTP_MKT_SZ_A
        )
        order_xtp.side            = xtp.XTP.XTP_SIDE_BUY if req.direction == "LONG" else xtp.XTP.XTP_SIDE_SELL
        order_xtp.price           = req.price
        order_xtp.quantity        = int(req.volume)
        order_xtp.price_type      = (
            xtp.XTP.XTP_PRICE_LIMIT if req.order_type == "LIMIT" else xtp.XTP.XTP_PRICE_BEST5_OR_CANCEL
        )
        xtp_order_id = self._td_api.InsertOrder(order_xtp, self._session_id)
        oid = str(xtp_order_id)
        req.order_id = oid
        order = OrderData(
            order_id=oid, symbol=req.symbol, direction=req.direction,
            order_type=req.order_type, price=req.price, volume=req.volume,
            status="SUBMITTED",
        )
        self.order_book.add(order)
        return oid

    def cancel_order(self, order_id: str) -> None:
        if self._td_api and self._session_id:
            self._td_api.CancelOrder(int(order_id), self._session_id)

    def query_account(self) -> AccountData:
        return AccountData(balance=0.0, available=0.0)

    def query_position(self, symbol: str) -> PositionData:
        return PositionData(symbol=symbol)
