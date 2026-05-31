"""CPU-vs-GPU scaling benchmark for the optimizer's reward kernel.

This is the number for the "Spark Story": it proves the GPU is *load-bearing in the
hot loop*, not just preprocessing. It times `_layout_terms` — the dense (D demand
cells × S candidate stops) gravity/distance kernel the greedy search calls thousands
of times — on NumPy (CPU) and, when available, CuPy (GPU), over a rising batch of
candidate stops, and prints a scaling table + the headline speedup.

Run from `backend/`:

    # CPU only (laptop): shows the CPU column and reports GPU as unavailable.
    .venv/Scripts/python.exe scripts/bench_reward.py

    # On the DGX Spark (CuPy installed): full CPU-vs-GPU scaling.
    .venv/bin/python scripts/bench_reward.py

It uses the REAL Toronto demand grid from get_city_grid (same D the optimizer sees),
so the timing is honest, not synthetic. Quote the GPU/CPU speedup at the largest S.
"""

from __future__ import annotations

import sys
import time

import numpy as np

from app.tools._gpu import get_backend
from app.tools.optimization import _layout_terms, _load_grid_features

# Candidate-batch sizes to sweep. The kernel cost is O(D × S); larger S is exactly
# where a CPU stalls and the GPU's batched tensor cores pull ahead.
_S_VALUES = (1, 2, 4, 8, 16, 32, 64, 128, 256)
_REPEATS = 50  # per S; median reported to shrug off jitter


def _bench(xp, feats, slon_all, slat_all, s: int, repeats: int) -> float:
    """Median seconds for one `_layout_terms` call with S=s stops, on backend xp."""
    demand_lon = xp.asarray(feats.demand_lon)
    demand_lat = xp.asarray(feats.demand_lat)
    pop = xp.asarray(feats.pop)
    need = xp.asarray(feats.need)
    access0 = xp.asarray(feats.access0)
    nearest0 = xp.asarray(feats.nearest0)
    reach = xp.asarray(feats.reach)
    slon = xp.asarray(slon_all[:s])
    slat = xp.asarray(slat_all[:s])

    is_cupy = xp.__name__ == "cupy"

    def sync() -> None:
        if is_cupy:
            xp.cuda.Stream.null.synchronize()

    # Warm up (JIT/alloc) so we time steady state, not first-call overhead.
    _layout_terms(demand_lon, demand_lat, pop, need, access0, nearest0, reach,
                  slon, slat, xp)
    sync()

    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _layout_terms(demand_lon, demand_lat, pop, need, access0, nearest0, reach,
                      slon, slat, xp)
        sync()
        samples.append(time.perf_counter() - t0)
    return float(np.median(samples))


def main() -> int:
    backend = get_backend()
    feats = _load_grid_features()
    d = feats.pop.shape[0]
    print(f"Demand cells D = {d:,}  (real Toronto grid from get_city_grid)")
    print(f"Resolved backend: {backend.name}\n")

    # A fixed pool of candidate stop coords spread across the grid bbox.
    rng = np.random.default_rng(0)
    lon_lo, lon_hi = feats.demand_lon.min(), feats.demand_lon.max()
    lat_lo, lat_hi = feats.demand_lat.min(), feats.demand_lat.max()
    slon_all = rng.uniform(lon_lo, lon_hi, max(_S_VALUES))
    slat_all = rng.uniform(lat_lo, lat_hi, max(_S_VALUES))

    have_gpu = backend.is_gpu
    if not have_gpu:
        try:
            import cupy  # noqa: F401
            have_gpu = True
            import cupy as gpu_xp
        except Exception:
            gpu_xp = None
    else:
        gpu_xp = backend.xp

    print(f"{'S':>5} {'CPU ms':>10} {'GPU ms':>10} {'speedup':>9}")
    print("-" * 38)
    last_speedup = None
    for s in _S_VALUES:
        cpu_s = _bench(np, feats, slon_all, slat_all, s, _REPEATS) * 1e3
        if gpu_xp is not None:
            gpu_s = _bench(gpu_xp, feats, slon_all, slat_all, s, _REPEATS) * 1e3
            speedup = cpu_s / gpu_s if gpu_s > 0 else float("inf")
            last_speedup = speedup
            print(f"{s:>5} {cpu_s:>10.3f} {gpu_s:>10.3f} {speedup:>8.1f}x")
        else:
            print(f"{s:>5} {cpu_s:>10.3f} {'n/a':>10} {'n/a':>9}")

    print()
    if gpu_xp is None:
        print("GPU: CuPy not available on this host — run on the DGX Spark "
              "(pip install cupy-cuda13x) for the GPU column.")
    elif last_speedup is not None:
        print(f"Headline: {last_speedup:.1f}x faster on GPU at S={max(_S_VALUES)} "
              f"(D={d:,}). This is the kernel the greedy search calls thousands of "
              f"times per optimisation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
