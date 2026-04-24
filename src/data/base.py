from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class BaseDataFeed(ABC):
    """Abstract data source. All feeds must implement fetch_bars()."""

    @abstractmethod
    def fetch_bars(
        self,
        symbol: str,
        interval: str = "daily",
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame indexed by date with columns:
        open, high, low, close, volume
        """

    @abstractmethod
    def name(self) -> str:
        """Unique name for this data source."""
