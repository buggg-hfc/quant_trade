"""FastAPI + WebSocket live server.

Broadcasts real-time events (orders, trades, ticks, account, positions) to
all connected WebSocket clients. The live_ui/index.html page consumes this.

Start via launcher.py or directly:
    uvicorn src.monitor.live_server:app --port 8000

IMPORTANT: This server must NOT auto-restart on crash (live positions may be
in memory). See launcher.py crash policy and CLAUDE.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

logger = logging.getLogger(__name__)

app = FastAPI(title="quant_trade live server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory state (reset on process restart) ────────────────────────────────

_state: dict[str, Any] = {
    "account": {"balance": 0.0, "available": 0.0, "total_pnl": 0.0},
    "positions": {},
    "open_orders": [],
    "recent_trades": [],   # last 100
    "last_ticks": {},
    "system_status": "idle",
    "connected_gateway": None,
    "started_at": datetime.now().isoformat(),
}

# ── WebSocket connection manager ──────────────────────────────────────────────

class _ConnectionManager:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        logger.info(f"WS client connected (total={len(self._clients)})")

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws) if hasattr(self._clients, "discard") else None
        if ws in self._clients:
            self._clients.remove(ws)
        logger.info(f"WS client disconnected (total={len(self._clients)})")

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


_mgr = _ConnectionManager()


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    ui_path = Path(__file__).parent / "live_ui" / "index.html"
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>quant_trade live server running</h2><p>Live UI not found.</p>")


@app.get("/state")
async def get_state():
    return _state


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(_mgr._clients)}


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await _mgr.connect(ws)
    # Send current state snapshot on connect
    await ws.send_json({"type": "snapshot", "data": _state})
    try:
        while True:
            # Keep connection alive; client messages are ignored
            await ws.receive_text()
    except WebSocketDisconnect:
        _mgr.disconnect(ws)


# ── Publisher API (called by live trading engine) ─────────────────────────────

async def _push(event_type: str, data: Any) -> None:
    await _mgr.broadcast({"type": event_type, "data": data, "ts": datetime.now().isoformat()})


def publish_account(balance: float, available: float, pnl: float) -> None:
    _state["account"] = {"balance": balance, "available": available, "total_pnl": pnl}
    asyncio.create_task(_push("account", _state["account"]))


def publish_position(symbol: str, net_vol: float, avg_price: float) -> None:
    _state["positions"][symbol] = {"net_volume": net_vol, "avg_price": avg_price}
    asyncio.create_task(_push("position", {"symbol": symbol, **_state["positions"][symbol]}))


def publish_order(order_id: str, symbol: str, direction: str,
                  status: str, price: float, volume: float) -> None:
    order = {
        "order_id": order_id, "symbol": symbol, "direction": direction,
        "status": status, "price": price, "volume": volume,
    }
    _state["open_orders"] = [o for o in _state["open_orders"] if o["order_id"] != order_id]
    if status in ("SUBMITTED", "ACCEPTED", "PARTIAL"):
        _state["open_orders"].append(order)
    asyncio.create_task(_push("order", order))


def publish_trade(symbol: str, direction: str, price: float,
                  volume: float, commission: float) -> None:
    trade = {
        "symbol": symbol, "direction": direction, "price": price,
        "volume": volume, "commission": commission,
        "ts": datetime.now().isoformat(),
    }
    _state["recent_trades"] = ([trade] + _state["recent_trades"])[:100]
    asyncio.create_task(_push("trade", trade))


def publish_tick(symbol: str, last: float, bid: float, ask: float) -> None:
    _state["last_ticks"][symbol] = {"last": last, "bid": bid, "ask": ask}
    asyncio.create_task(_push("tick", {"symbol": symbol, **_state["last_ticks"][symbol]}))


def set_status(status: str, gateway: str | None = None) -> None:
    _state["system_status"] = status
    if gateway:
        _state["connected_gateway"] = gateway
    asyncio.create_task(_push("status", {"status": status, "gateway": gateway}))
