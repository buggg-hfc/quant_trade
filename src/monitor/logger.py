from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def init_logger(log_level: str = "INFO", log_dir: str | Path | None = None) -> None:
    logger.remove()
    logger.add(sys.stderr, level=log_level, colorize=True,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}")

    if log_dir:
        log_path = Path(log_dir) / "quant_trade_{time:YYYY-MM-DD}.log"
        logger.add(str(log_path), level=log_level, rotation="00:00", retention="30 days",
                   encoding="utf-8")
