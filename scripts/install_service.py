"""Windows Service registration for quant_trade live server.

Registers the FastAPI live server as a Windows Service so it starts
automatically on boot and restarts on crash.

Usage (must be run as Administrator):
    python scripts/install_service.py --install
    python scripts/install_service.py --remove
    python scripts/install_service.py --start
    python scripts/install_service.py --stop
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _require_pywin32():
    try:
        import win32serviceutil  # type: ignore
        return win32serviceutil
    except ImportError:
        print("ERROR: pywin32 not installed. Run: pip install pywin32")
        sys.exit(1)


def _require_windows():
    if sys.platform != "win32":
        print("ERROR: Windows service registration is only supported on Windows.")
        sys.exit(1)


class QuantTradeLiveService:
    """Windows Service wrapper for the FastAPI live server."""

    _svc_name_ = "QuantTradeLive"
    _svc_display_name_ = "quant_trade Live Server"
    _svc_description_ = (
        "quant_trade real-time trading server (FastAPI + WebSocket). "
        "Broadcasts orders, trades, and positions to the live dashboard."
    )

    def SvcStop(self):
        import win32service  # type: ignore
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_event.set()

    def SvcDoRun(self):
        import threading
        import uvicorn  # type: ignore

        self._stop_event = threading.Event()

        def run():
            uvicorn.run(
                "src.monitor.live_server:app",
                host="0.0.0.0",
                port=8000,
                log_level="info",
            )

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self._stop_event.wait()


def install():
    _require_windows()
    wsutil = _require_pywin32()
    exe = sys.executable
    script = str(ROOT / "scripts" / "install_service.py")
    wsutil.InstallService(
        QuantTradeLiveService._svc_name_,
        QuantTradeLiveService._svc_display_name_,
        f'"{exe}" "{script}" --run-service',
        startType=2,   # AUTO_START
        description=QuantTradeLiveService._svc_description_,
    )
    print(f"Service '{QuantTradeLiveService._svc_name_}' installed.")


def remove():
    _require_windows()
    wsutil = _require_pywin32()
    try:
        wsutil.StopService(QuantTradeLiveService._svc_name_)
    except Exception:
        pass
    wsutil.RemoveService(QuantTradeLiveService._svc_name_)
    print(f"Service '{QuantTradeLiveService._svc_name_}' removed.")


def start():
    _require_windows()
    wsutil = _require_pywin32()
    wsutil.StartService(QuantTradeLiveService._svc_name_)
    print("Service started.")


def stop():
    _require_windows()
    wsutil = _require_pywin32()
    wsutil.StopService(QuantTradeLiveService._svc_name_)
    print("Service stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="quant_trade Windows Service manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install",     action="store_true")
    group.add_argument("--remove",      action="store_true")
    group.add_argument("--start",       action="store_true")
    group.add_argument("--stop",        action="store_true")
    group.add_argument("--run-service", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.install:
        install()
    elif args.remove:
        remove()
    elif args.start:
        start()
    elif args.stop:
        stop()
    elif args.run_service:
        # Invoked by the service control manager
        _require_windows()
        _require_pywin32()
        import win32serviceutil  # type: ignore
        win32serviceutil.HandleCommandLine(QuantTradeLiveService)
