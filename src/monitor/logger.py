"""Loguru logger initialization.

Call init_logger() once at startup. All subsequent `from loguru import logger`
imports share the same configured instance.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def init_logger(log_level: str = "INFO", log_dir: Optional[str | Path] = None) -> None:
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
    )
    logger.add(sys.stderr, level=log_level, colorize=True, format=fmt)

    if log_dir:
        log_path = Path(log_dir) / "quant_{time:YYYY-MM-DD}.log"
        logger.add(
            str(log_path),
            level=log_level,
            rotation="00:00",
            retention="30 days",
            encoding="utf-8",
            format=fmt,
        )
        # Separate data quality log
        dq_path = Path(log_dir) / "data_quality.log"
        logger.add(
            str(dq_path),
            level="WARNING",
            filter=lambda r: "data_quality" in r["extra"],
            rotation="10 MB",
            retention="90 days",
            encoding="utf-8",
        )
