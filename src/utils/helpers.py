from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path


def now_ts() -> int:
    """Return current UTC Unix timestamp in seconds."""
    return int(time.time())


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_root() -> Path:
    return Path(__file__).parent.parent.parent


def data_cache_dir() -> Path:
    return ensure_dir(project_root() / "data_cache")


def logs_dir() -> Path:
    return ensure_dir(project_root() / "logs")


def reports_dir() -> Path:
    return ensure_dir(project_root() / "reports")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
