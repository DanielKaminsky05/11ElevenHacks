"""Array-backend resolver: NumPy on a laptop, CuPy on the DGX Spark.

The reward eval (app/tools/optimization.py) is the optimizer's hot loop — a dense
distance/gravity computation over every demand cell × every candidate stop, run
thousands of times per search. That math is backend-agnostic: written against an
``xp`` array module, it runs unchanged on NumPy (CPU) or CuPy (GPU).

`get_backend()` picks the backend once:

  - ``TRANSITRL_REWARD_BACKEND=cpu``  → always NumPy.
  - ``TRANSITRL_REWARD_BACKEND=gpu``  → CuPy, error out loud if it can't load.
  - ``TRANSITRL_REWARD_BACKEND=auto`` (default) → CuPy if importable and a device is
    present (the Spark), else NumPy (a laptop). So tests and laptop dev stay on
    NumPy with zero config, and the same code is GPU-resident on the Spark.

Keeping this in one tiny module means the optimizer never imports cupy directly and
never branches on hardware in its hot path — it just asks for ``backend.xp``.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Backend:
    """The chosen array module and a human-readable name ('cpu' | 'gpu')."""

    xp: Any
    name: str

    @property
    def is_gpu(self) -> bool:
        return self.name == "gpu"


def _try_cupy() -> Any | None:
    """Return the cupy module if it imports AND a CUDA device is actually usable,
    else None. Importing cupy can succeed on a box with no driver, so we touch the
    device to be sure before committing the hot loop to it."""
    try:
        cp = importlib.import_module("cupy")
        cp.zeros(1)  # forces device init; raises if no usable CUDA device
        return cp
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_backend() -> Backend:
    """Resolve the array backend once (cached). See module docstring for modes."""
    mode = os.environ.get("TRANSITRL_REWARD_BACKEND", "auto").strip().lower()

    if mode == "cpu":
        return Backend(np, "cpu")

    cp = _try_cupy()
    if cp is not None:
        return Backend(cp, "gpu")

    if mode == "gpu":
        raise RuntimeError(
            "TRANSITRL_REWARD_BACKEND=gpu but CuPy/CUDA is unavailable. "
            "Install cupy-cuda13x on the DGX Spark, or unset to fall back to CPU."
        )
    return Backend(np, "cpu")


def asnumpy(x: Any) -> np.ndarray:
    """Bring an array back to host NumPy regardless of backend (cupy.asnumpy / np)."""
    get = getattr(type(x), "get", None)
    if get is not None and x.__class__.__module__.startswith("cupy"):
        return x.get()
    return np.asarray(x)
