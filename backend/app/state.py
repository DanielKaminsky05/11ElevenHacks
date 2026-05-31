"""Shared, process-wide state held on `app.state` and populated in the lifespan.

The city grid is loaded ONCE at startup and kept resident — every request reuses
the in-memory tensor instead of reloading from disk. On the Spark this is the
concrete realization of the "128 GB unified memory" design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Singletons shared across requests. Access via the `app_state` dependency."""

    grid_loaded: bool = False
    grid: object | None = None  # the multi-channel city tensor (GPU-resident on the Spark)


def load_city_grid(state: AppState, *, data_dir: str, resolution: int) -> None:
    """Rasterize the open-data layers into the city grid.

    STUB: deferred until the data/compute layer lands. Intentionally does NOT
    import any GPU library, so the app boots on a non-GPU laptop. On the Spark
    this will use RAPIDS cuDF/cuSpatial to rasterize once into unified memory.
    """
    logger.info(
        "city grid load deferred (stub) — data_dir=%s resolution=%d",
        data_dir,
        resolution,
    )
    state.grid_loaded = False
