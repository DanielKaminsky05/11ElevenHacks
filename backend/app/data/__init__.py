"""Shared data-access helpers for tools.

Tools should load open-data layers through helpers here (cached), not by
re-reading files on every call. Resolves paths relative to the configured
data directory. Add loaders as families need them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import get_settings


def data_dir() -> Path:
    """Absolute path to the open-data directory (TRANSITRL_DATA_DIR)."""
    root = Path(__file__).resolve().parents[2]  # backend/
    return (root / get_settings().data_dir).resolve()


@lru_cache(maxsize=64)
def resolve(*parts: str) -> Path:
    """Resolve and validate a path under the data directory."""
    p = data_dir().joinpath(*parts)
    if not p.exists():
        raise FileNotFoundError(f"data file not found: {p}")
    return p
