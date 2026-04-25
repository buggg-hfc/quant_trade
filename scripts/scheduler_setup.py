"""Windows Task Scheduler setup for quant_trade.

Creates scheduled tasks so the system starts/stops automatically:
  - A-share / Futures: start 09:25, stop 15:05 (Mon–Fri)
  - Crypto:            continuous 24/7 (optional)

Usage (must be run as Administrator):
    python scripts/scheduler_setup.py --install
    python scripts/scheduler_setup.py --remove
    python scripts/scheduler_setup.py --install --crypto   # include crypto 24/7 task
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
LAUNCHER = str(ROOT / "launcher.py")

# Task definitions: (name, action_cmd, schedule_xml_fragment)
_TASK_START_ASHARE = "QuantTrade_AShare_Start"
_TASK_STOP_ASHARE  = "QuantTrade_AShare_Stop"
_TASK_CRYPTO       = "QuantTrade_Crypto_24x7"


def _require_windows():
    if sys.platform != "win32":
        print("ERROR: Task Scheduler setup only works on Windows.")
        sys.exit(1)


def _schtasks(args: list[str]) -> int:
    cmd = ["schtasks"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"schtasks error: {result.stderr.strip()}")
    return result.returncode


def _create_task(name: str, cmd: str, time_str: str, days: str = "MON,TUE,WED,THU,FRI") -> None:
    """Create a daily scheduled task."""
    _schtasks([
        "/Create", "/F",
        "/TN", name,
        "/TR", cmd,
        "/SC", "WEEKLY",
        "/D", days,
        "/ST", time_str,
        "/RU", "SYSTEM",
        "/RL", "HIGHEST",
    ])
    print(f"Created task: {name} @ {time_str} ({days})")


def install(include_crypto: bool = False) -> None:
    _require_windows()

    # Start GUI + live server at 09:25 (Mon–Fri)
    _create_task(
        _TASK_START_ASHARE,
        f'"{PYTHON}" "{LAUNCHER}"',
        "09:25",
    )

    # Stop all processes at 15:05 (Mon–Fri)
    _create_task(
        _TASK_STOP_ASHARE,
        f'taskkill /F /IM python.exe /T',
        "15:05",
    )

    if include_crypto:
        # Crypto 24/7 — restart daily at midnight to clear memory
        _schtasks([
            "/Create", "/F",
            "/TN", _TASK_CRYPTO,
            "/TR", f'"{PYTHON}" "{LAUNCHER}" --live-only',
            "/SC", "DAILY",
            "/ST", "00:01",
            "/RU", "SYSTEM",
            "/RL", "HIGHEST",
        ])
        print(f"Created task: {_TASK_CRYPTO} @ 00:01 daily")

    print("\nAll tasks created. Verify with: schtasks /Query /TN QuantTrade*")


def remove() -> None:
    _require_windows()
    for name in [_TASK_START_ASHARE, _TASK_STOP_ASHARE, _TASK_CRYPTO]:
        ret = _schtasks(["/Delete", "/F", "/TN", name])
        if ret == 0:
            print(f"Removed task: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Windows Task Scheduler setup for quant_trade")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true")
    group.add_argument("--remove",  action="store_true")
    parser.add_argument("--crypto", action="store_true", help="Also create 24/7 crypto task")
    args = parser.parse_args()

    if args.install:
        install(include_crypto=args.crypto)
    elif args.remove:
        remove()
