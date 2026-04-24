"""
Launcher: manages Streamlit (GUI) and FastAPI (live server) as subprocesses.

Crash policy:
  - Streamlit crash → auto-restart (stateless GUI).
  - FastAPI crash  → ALERT ONLY, no auto-restart. Live positions may be in memory;
                     restart manually after confirming positions:
                     python launcher.py --live-only
"""
from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time

from loguru import logger

STREAMLIT_PORT = 8501
FASTAPI_PORT = 8000

STREAMLIT_CMD = [sys.executable, "-m", "streamlit", "run",
                 "src/monitor/dashboard.py", "--server.port", str(STREAMLIT_PORT)]
FASTAPI_CMD = [sys.executable, "-m", "uvicorn",
               "src.monitor.live_server:app", "--port", str(FASTAPI_PORT)]


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _check_ports() -> None:
    for port, name in [(STREAMLIT_PORT, "Streamlit"), (FASTAPI_PORT, "FastAPI")]:
        if _port_in_use(port):
            logger.error(f"Port {port} ({name}) already in use. Stop the existing process first.")
            sys.exit(1)


def run(gui_only: bool = False, live_only: bool = False) -> None:
    _check_ports()

    procs: dict[str, subprocess.Popen] = {}
    stop_event = False

    def shutdown(sig, frame):
        nonlocal stop_event
        logger.info("Shutting down...")
        stop_event = True
        for name, p in procs.items():
            p.terminate()
            logger.info(f"{name} terminated")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not live_only:
        procs["Streamlit"] = subprocess.Popen(STREAMLIT_CMD)
        logger.info(f"Streamlit started (pid={procs['Streamlit'].pid}) on :{STREAMLIT_PORT}")

    if not gui_only:
        procs["FastAPI"] = subprocess.Popen(FASTAPI_CMD)
        logger.info(f"FastAPI started (pid={procs['FastAPI'].pid}) on :{FASTAPI_PORT}")

    while not stop_event:
        time.sleep(2)
        for name, p in list(procs.items()):
            ret = p.poll()
            if ret is not None:
                if name == "Streamlit":
                    logger.warning(f"Streamlit exited (code={ret}). Restarting...")
                    procs["Streamlit"] = subprocess.Popen(STREAMLIT_CMD)
                elif name == "FastAPI":
                    # FastAPI crash: alert only — do not auto-restart (live positions may be lost)
                    logger.error(
                        f"FastAPI CRASHED (code={ret}). NOT auto-restarting. "
                        "Confirm live positions before restarting manually: "
                        "python launcher.py --live-only"
                    )
                    del procs["FastAPI"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="quant_trade launcher")
    parser.add_argument("--gui-only", action="store_true", help="Start Streamlit only")
    parser.add_argument("--live-only", action="store_true", help="Start FastAPI only")
    args = parser.parse_args()
    run(gui_only=args.gui_only, live_only=args.live_only)
