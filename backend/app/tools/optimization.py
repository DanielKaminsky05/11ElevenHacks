"""TransitRL tools — Family D: Optimization.

Tools that let the machine search: parse_goal, optimize_layout,
propose_candidates, optimization_status. Register each with `@tool` from
app.tools.registry.

The optimizer is **greedy + local search**, not RL: stop placement is a maximal
covering / p-median problem whose coverage objective is monotone submodular, so
greedy is provably within (1 - 1/e) of optimal, deterministic, and fast enough to
re-solve interactively when the planner changes weights. See
docs/reward-and-optimizer.md.

The reward is grounded in real per-cell data (population, low-income "need",
existing-network access) pulled from get_city_grid, and credits only *new* access
(gravity decay), so the optimizer closes gaps instead of piling onto already-
served areas. Reward eval is the bottleneck and is embarrassingly parallel, so its
hot loop runs on whichever array backend is present — NumPy on a laptop, CuPy on the
Spark's GPU (see app/tools/_gpu.py and scripts/bench_reward.py).

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Point
from shapely.ops import unary_union

from app.agent.nim_client import get_nim_client
from app.tools._demand import opportunity_access_normalised
from app.tools._gpu import get_backend
from app.tools.city_state import (
    GetCityGridArgs,
    _load_neighbourhoods,
    _resolve_neighbourhood_name,
    get_city_grid,
)
from app.tools.registry import tool
from app.tools.simulation import _load_route_shapes


# ---------------------------------------------------------------------------
# Shared domain models
# ---------------------------------------------------------------------------


class RewardSpec(BaseModel):
    """Structured reward specification produced by parse_goal and consumed by
    optimize_layout and propose_candidates.

    Weights are each in [0, 1].  They need not sum to 1 — the optimizer
    normalises them internally.
    """

    coverage_weight: float = Field(
        0.4, ge=0.0, le=1.0, description="Weight for population-coverage term"
    )
    travel_weight: float = Field(
        0.2, ge=0.0, le=1.0, description="Weight for average-travel-distance term (lower = better)"
    )
    equity_weight: float = Field(
        0.3, ge=0.0, le=1.0, description="Weight for equity / underserved-area term"
    )
    constraint_weight: float = Field(
        0.1, ge=0.0, le=1.0, description="Weight for feasibility-constraint penalty term"
    )
    region: str = Field(
        "Toronto",
        min_length=1,
        description="Name of the target region or neighbourhood",
    )
    budget: int = Field(
        5, gt=0, description="Maximum number of new or relocated stops"
    )
    protect: str | None = Field(
        None,
        description="Optional comma-separated list of corridors/areas to protect (do not worsen)",
    )

    @model_validator(mode="after")
    def at_least_one_nonzero_weight(self) -> "RewardSpec":
        total = (
            self.coverage_weight
            + self.travel_weight
            + self.equity_weight
            + self.constraint_weight
        )
        if total == 0.0:
            raise ValueError("At least one reward weight must be > 0")
        return self


# ---------------------------------------------------------------------------
# In-memory job store for optimization_status
# ---------------------------------------------------------------------------

_JOBS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Grid + tuning constants
# ---------------------------------------------------------------------------

# Coarse candidate grid: where a stop *can* be placed. Outputs map to lon/lat
# via _cell_to_lonlat. Kept stable so lon/lat outputs are reproducible.
_TORONTO_GRID_BOUNDS = {
    "lon_min": -79.6393,
    "lon_max": -79.1167,
    "lat_min": 43.5810,
    "lat_max": 43.8555,
}
_GRID_COLS = 20
_GRID_ROWS = 15

# Metres per degree at Toronto's latitude (matches diagnostics/simulation).
_M_PER_DEG_LAT = 111_139.0
_M_PER_DEG_LON = 111_139.0 * math.cos(math.radians(43.7))

# Demand grid resolution sampled from get_city_grid for the per-cell features.
# ~60 → ~750 m cells, fine enough that a stop's ~400 m walkshed is representable
# and suburban interiors far from arterial stops register as gaps.
_DEMAND_RESOLUTION = 60

# Gravity walk-access scale (metres): a stop's contribution to a cell's access
# fades with walk distance. ~400 m is the real walk-to-transit scale.
_D0_M = 400.0

# Per-stop cost λ: every extra stop must earn more than this marginal reward gain
# or greedy stops adding. Makes parsimony intrinsic, not just a hard budget cap.
# This is the knob to "play with" — λ=0 fills to budget; larger λ → fewer stops.
# In "% of the budget-achievable best" units: a stop must add more than ~2% of
# what the budget could ideally capture, or greedy stops adding it.
_LAMBDA_STOP_COST = 0.02

# Minimum spacing (metres) between *new* stops before the constraint term docks
# them. New-vs-existing redundancy is handled by gained-access saturation, not
# here — so legitimate transfer points (crossing routes) are never penalised.
_NEW_STOP_MIN_SPACING_M = 150.0

# A candidate cell is a "logical" stop site only if within this distance of an
# existing route line (on the street/transit network, not a ravine or rail yard).
_CANDIDATE_MAX_ROUTE_DIST_M = 700.0

# Fallback nearest-stop distance (metres) for cells with no existing stop nearby.
_NO_STOP_NEAREST_M = 10_000.0

_EPS = 1e-12


def _grid_cells() -> list[tuple[int, int]]:
    """Return all (row, col) indices of the coarse candidate grid."""
    return [(r, c) for r in range(_GRID_ROWS) for c in range(_GRID_COLS)]


def _cell_to_lonlat(row: int, col: int) -> tuple[float, float]:
    lon = (
        _TORONTO_GRID_BOUNDS["lon_min"]
        + (col + 0.5)
        * (_TORONTO_GRID_BOUNDS["lon_max"] - _TORONTO_GRID_BOUNDS["lon_min"])
        / _GRID_COLS
    )
    lat = (
        _TORONTO_GRID_BOUNDS["lat_min"]
        + (row + 0.5)
        * (_TORONTO_GRID_BOUNDS["lat_max"] - _TORONTO_GRID_BOUNDS["lat_min"])
        / _GRID_ROWS
    )
    return lon, lat


def _lonlat_to_cell(lon: float, lat: float) -> tuple[float, float]:
    """Inverse of _cell_to_lonlat: map a lon/lat to FRACTIONAL (row, col) on the
    candidate grid. Fractional indices are valid — _cell_to_lonlat is linear, so the
    optimiser scores and renders a fractional cell at exactly this lon/lat. This is
    what lets region candidates be placed anywhere inside a polygon, not just on the
    coarse ~2 km cell centres."""
    col = (lon - _TORONTO_GRID_BOUNDS["lon_min"]) / (
        _TORONTO_GRID_BOUNDS["lon_max"] - _TORONTO_GRID_BOUNDS["lon_min"]
    ) * _GRID_COLS - 0.5
    row = (lat - _TORONTO_GRID_BOUNDS["lat_min"]) / (
        _TORONTO_GRID_BOUNDS["lat_max"] - _TORONTO_GRID_BOUNDS["lat_min"]
    ) * _GRID_ROWS - 0.5
    return (row, col)


# ---------------------------------------------------------------------------
# Logical-location candidate filter
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _land_union():
    """Union of the Neighbourhoods-158 polygons — the 'on land / in city' mask."""
    gdf = _load_neighbourhoods()
    return unary_union(list(gdf.geometry.values))


@lru_cache(maxsize=1)
def _logical_candidate_cells() -> tuple[tuple[int, int], ...]:
    """Candidate cells filtered to plausible stop sites: on land (inside a Toronto
    neighbourhood) and near the existing street/route network. Drops water,
    ravines, rail yards, and out-of-city cells.

    # TODO: upgrade the network test to the Pedestrian Network + Centreline layers
    # (both already in data/geospatial/) for finer walkability.
    """
    land = _land_union()
    try:
        routes = _load_route_shapes("ttc-routes-schedules-gtfs")
    except FileNotFoundError:
        routes = None
    max_route_deg = _CANDIDATE_MAX_ROUTE_DIST_M / _M_PER_DEG_LAT
    has_routes = routes is not None and len(getattr(routes, "geoms", [])) > 0

    out: list[tuple[int, int]] = []
    for r, c in _grid_cells():
        lon, lat = _cell_to_lonlat(r, c)
        pt = Point(lon, lat)
        if not land.contains(pt):
            continue
        if has_routes and routes.distance(pt) > max_route_deg:
            continue
        out.append((r, c))
    return tuple(out)


# ---------------------------------------------------------------------------
# Region masking — confine placement to the area the planner actually named
# ---------------------------------------------------------------------------

# Names that mean "the whole city" → no spatial restriction.
_CITYWIDE_REGION_NAMES = frozenset(
    {"", "toronto", "city of toronto", "the city", "city-wide", "citywide", "all"}
)

# Buffers (degrees ≈ 1.1 km each) tried in turn when a named region is finer than
# the ~2 km candidate grid and contains too few cell centres on its own.
_REGION_BUFFER_STEPS_DEG = (0.01, 0.02, 0.04, 0.08)

# Roughly how many fine candidate points to scatter inside a named region, and the
# floor on spacing (~275 m). A neighbourhood smaller than one coarse grid cell still
# gets a dense set of in-polygon sites, so placed stops land INSIDE the area.
_REGION_FINE_TARGET = 160
_REGION_FINE_MIN_STEP_DEG = 0.0025


def _fine_region_cells(poly) -> tuple[tuple[float, float], ...]:
    """Fractional (row, col) candidates whose lon/lat fall INSIDE the region polygon.

    The step adapts to the region's size (bounded point count) so a tiny
    neighbourhood gets a dense in-polygon grid while a large district stays cheap.
    """
    minlon, minlat, maxlon, maxlat = poly.bounds
    width = max(maxlon - minlon, 1e-9)
    height = max(maxlat - minlat, 1e-9)
    step = max(
        _REGION_FINE_MIN_STEP_DEG, math.sqrt(width * height / _REGION_FINE_TARGET)
    )
    out: list[tuple[float, float]] = []
    for lon in np.arange(minlon + step / 2, maxlon, step):
        for lat in np.arange(minlat + step / 2, maxlat, step):
            if poly.contains(Point(float(lon), float(lat))):
                out.append(_lonlat_to_cell(float(lon), float(lat)))
    return tuple(out)


@lru_cache(maxsize=64)
def _region_polygon(region: str):
    """Resolve a region/neighbourhood name to its polygon (WGS84), or None.

    None means 'no spatial restriction' — an empty/citywide name, or a name that
    matches no neighbourhood (better to search the whole city than to error). A
    district name that matches several neighbourhoods (e.g. 'Scarborough') returns
    the union of all of them, so the whole district is in scope.
    """
    if region.strip().lower() in _CITYWIDE_REGION_NAMES:
        return None
    gdf = _load_neighbourhoods()
    lower = region.strip().lower()
    mask = gdf["AREA_NAME"].str.lower().str.contains(lower, regex=False)
    matches = gdf[mask]
    if not matches.empty:
        return unary_union(list(matches.geometry.values))
    # No substring hit — tolerate a misspelling by snapping to the closest name
    # (e.g. "Clanton Rock" → "Clanton Park") so placement still targets the right
    # area instead of silently falling back to city-wide.
    canonical = _resolve_neighbourhood_name(region)
    if canonical is None:
        return None
    return unary_union(list(gdf[gdf["AREA_NAME"] == canonical].geometry.values))


def _region_candidates(
    region: str, candidates: tuple[tuple[int, int], ...], min_count: int
) -> tuple[tuple[tuple[int, int], ...], bool]:
    """Restrict candidate stop cells to those inside the named region.

    Returns (cells, restricted). `restricted` is False when no spatial mask was
    applied (citywide name, or an unmatched name → search everywhere).

    The candidate grid is coarse (~2 km cells), so a single small neighbourhood
    can contain too few cell centres to place `min_count` stops. When that happens
    we grow a buffer around the region until enough cells fall inside — keeping the
    search local to the area without ever returning fewer candidates than the
    budget needs. Only if even a generous buffer is too sparse do we fall back to
    the full city (restricted=False), so the optimiser always has somewhere to go.
    """
    poly = _region_polygon(region)
    if poly is None:
        return candidates, False

    # Preferred: a fine grid of sites INSIDE the polygon, so stops land within the
    # neighbourhood instead of on a coarse ~2 km cell centre that sits just outside.
    fine = _fine_region_cells(poly)
    if fine:
        return fine, True

    # Polygon too thin to catch a fine point — fall back to the coarse cells inside
    # it, then grow a buffer until we have enough to place the budget.
    points = {cell: Point(*_cell_to_lonlat(*cell)) for cell in candidates}
    target = max(min_count, 3)

    inside = tuple(cell for cell, pt in points.items() if poly.contains(pt))
    if len(inside) >= target:
        return inside, True

    for buffer_deg in _REGION_BUFFER_STEPS_DEG:
        grown = poly.buffer(buffer_deg)
        near = tuple(cell for cell, pt in points.items() if grown.contains(pt))
        if len(near) >= target:
            return near, True

    # Region is too fine even for the widest buffer — keep whatever we found inside
    # if any, else give up the restriction rather than return nothing to place.
    if inside:
        return inside, True
    return candidates, False


# ---------------------------------------------------------------------------
# Per-cell demand features (grounded in real data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _GridFeatures:
    """Per-demand-cell features + fixed reference points for one optimisation.

    All arrays are aligned and cover demand cells with population > 0. Reward
    stays a pure function of (layout, spec, this struct) — the I/O happens here,
    once, cached.
    """

    demand_lon: np.ndarray  # (D,)
    demand_lat: np.ndarray  # (D,)
    pop: np.ndarray         # (D,) people
    need: np.ndarray        # (D,) low-income share, in [0, 1]
    access0: np.ndarray     # (D,) gravity access from the EXISTING network, [0,1]
    nearest0: np.ndarray    # (D,) metres to nearest existing stop
    reach: np.ndarray       # (D,) opportunity (job) access weight, [0,1] — the O-D
                            #      "demand" side: how many jobs/opportunities are
                            #      reachable from this cell's location. SAM-validated.
    pop_sum: float
    needpop_sum: float
    burden0: float          # do-nothing person-weighted walk burden (metre·people)
    # Descending cumulative sums of per-cell "instant gains" (value if a stop
    # landed on that cell). cumsum[k-1] = the best a budget of k stops could do,
    # ignoring overlap — an optimistic upper bound used to normalise each channel
    # to "% of the budget-achievable best". Fixed per goal.
    cov_cumsum: np.ndarray
    eq_cumsum: np.ndarray
    travel_cumsum: np.ndarray
    candidates: tuple[tuple[int, int], ...]


@lru_cache(maxsize=4)
def _load_grid_features(resolution: int = _DEMAND_RESOLUTION) -> _GridFeatures:
    """Build (and cache) the per-cell demand features from get_city_grid.

    Demand stays CITY-WIDE on purpose: a stop placed in a region is still scored
    against the people and gaps around it (its walkshed doesn't stop at the
    neighbourhood line). Region targeting is applied where it belongs — masking the
    *candidate* cells the optimiser may place into (see _region_candidates), not the
    demand it serves. # TODO: swap to a finer census-DA population raster.
    """
    g = get_city_grid(
        GetCityGridArgs(
            bbox=None, channels=["population", "need", "stops"], resolution=resolution
        )
    )
    pop = np.asarray(g["grid"]["population"], dtype=float).ravel()
    need = np.asarray(g["grid"]["need"], dtype=float).ravel()
    stops_grid = np.asarray(g["grid"]["stops"], dtype=float).ravel()

    lon_c = np.asarray(g["lon_centres"], dtype=float)
    lat_c = np.asarray(g["lat_centres"], dtype=float)
    lon_mesh, lat_mesh = np.meshgrid(lon_c, lat_c)  # grid[row=lat, col=lon] order
    demand_lon = lon_mesh.ravel()
    demand_lat = lat_mesh.ravel()

    # Existing-network access0 / nearest0: each cell holding existing stops is a
    # source at its own centre. Gravity access uses the nearest source (max over
    # sources) so cells near many stops don't accrue unbounded credit — and so a
    # cell more than a walkshed from any stop reads as a genuine gap.
    src = stops_grid > 0
    if src.any():
        sx = demand_lon[src]
        sy = demand_lat[src]
        dx = (demand_lon[:, None] - sx[None, :]) * _M_PER_DEG_LON
        dy = (demand_lat[:, None] - sy[None, :]) * _M_PER_DEG_LAT
        dist = np.sqrt(dx * dx + dy * dy)
        nearest0 = dist.min(axis=1)
        access0 = np.exp(-nearest0 / _D0_M)
    else:
        nearest0 = np.full_like(demand_lon, _NO_STOP_NEAREST_M)
        access0 = np.zeros_like(demand_lon)

    # Keep only populated cells — unpopulated cells contribute nothing and slow
    # the reward down.
    keep = pop > 0
    pop = pop[keep]
    need = need[keep]
    access0 = access0[keep]
    nearest0 = nearest0[keep]
    demand_lon = demand_lon[keep]
    demand_lat = demand_lat[keep]

    # Opportunity-access weight (the O-D demand side): how many jobs/opportunities
    # are reachable from each cell's location, in [0, 1]. Folds origin→destination
    # demand into the reward so a new stop is credited for the *opportunities* it
    # connects residents to — not merely for being walkable. Validated against
    # StatCan SAM's transit employment-access index (see app/tools/_demand.py).
    reach = opportunity_access_normalised(demand_lon, demand_lat)

    pop_sum = float(pop.sum())
    needpop = need * pop
    needpop_sum = float(needpop.sum())
    burden0 = float((pop * nearest0).sum())

    # Per-cell instant gains (value if a stop landed exactly on that cell):
    #   coverage = pop · (unserved fraction) · reach   (opportunity-weighted access)
    #   equity   = need · pop · (unserved fraction)    (need-weighted; NOT reach)
    #   travel   = pop · (metres removed ≈ its whole nearest-stop distance)
    # Coverage carries `reach` so its ideal normaliser is on the same opportunity-
    # weighted scale as the layout value below. Equity and travel stay orthogonal
    # to opportunity (equity serves need incl. transit deserts; travel is pure walk
    # burden).
    unserved = 1.0 - access0
    cov_cumsum = np.cumsum(np.sort(pop * unserved * reach)[::-1])
    eq_cumsum = np.cumsum(np.sort(need * pop * unserved)[::-1])
    travel_cumsum = np.cumsum(np.sort(pop * nearest0)[::-1])

    return _GridFeatures(
        demand_lon=demand_lon,
        demand_lat=demand_lat,
        pop=pop,
        need=need,
        access0=access0,
        nearest0=nearest0,
        reach=reach,
        pop_sum=pop_sum,
        needpop_sum=needpop_sum,
        burden0=burden0,
        cov_cumsum=cov_cumsum,
        eq_cumsum=eq_cumsum,
        travel_cumsum=travel_cumsum,
        candidates=_logical_candidate_cells(),
    )


# ---------------------------------------------------------------------------
# Reward function (pure: function of layout, spec, and per-cell features)
# ---------------------------------------------------------------------------


def _ratio(value: float, ideal: float) -> float:
    """Fraction of the achievable improvement captured (do_nothing baseline = 0).

    When there is no opportunity (ideal ≈ 0), the layout has nothing to improve,
    so it trivially captures all of it → 1.0. Otherwise clamp value/ideal to [0,1].
    """
    if ideal <= _EPS:
        return 1.0
    return float(min(max(value / ideal, 0.0), 1.0))


def _ideal_b(cumsum: np.ndarray, budget: int) -> float:
    """Best a budget of `budget` stops could capture (top-`budget` instant gains)."""
    if cumsum.size == 0:
        return 0.0
    return float(cumsum[min(budget, cumsum.size) - 1])


def _spacing_penalty(stops: list[tuple[int, int]]) -> float:
    """Fraction of *new-stop* pairs closer than the minimum spacing.

    Applies only among the new stops in the layout — never new-vs-existing, which
    is handled by gained-access saturation. So transfer points are not punished.
    """
    n = len(stops)
    if n < 2:
        return 0.0
    pts = [_cell_to_lonlat(r, c) for r, c in stops]
    too_close = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            dx = (pts[i][0] - pts[j][0]) * _M_PER_DEG_LON
            dy = (pts[i][1] - pts[j][1]) * _M_PER_DEG_LAT
            if math.hypot(dx, dy) < _NEW_STOP_MIN_SPACING_M:
                too_close += 1
    return too_close / pairs if pairs else 0.0


# Backend-agnostic device arrays for one optimisation: (demand_lon, demand_lat,
# pop, need, access0, nearest0, reach). On the Spark these live on the GPU.
_LayoutArrays = tuple


def _layout_terms(
    demand_lon, demand_lat, pop, need, access0, nearest0, reach, slon, slat, xp
) -> tuple[float, float, float]:
    """The reward hot loop, written against an array module ``xp`` so it runs
    unchanged on NumPy (CPU) or CuPy (GPU). Returns (cov_val, eq_val, burden_removed).

    This is the optimizer's inner kernel — a dense (D demand cells × S stops)
    distance/gravity computation evaluated thousands of times per search. It is
    exactly the embarrassingly-parallel, compute-bound work the Spark's GPU eats:
    no Python loops, all elementwise/reduction tensor ops, batchable over candidates.
    See app/tools/_gpu.py and scripts/bench_reward.py for the CPU-vs-GPU scaling.
    """
    dx = (demand_lon[:, None] - slon[None, :]) * _M_PER_DEG_LON
    dy = (demand_lat[:, None] - slat[None, :]) * _M_PER_DEG_LAT
    dist = xp.sqrt(dx * dx + dy * dy)  # (D, S)

    # Gravity access from the NEW stops; credit only access beyond the existing
    # network (saturation → a stop near already-served demand earns ~0, a stop in a
    # thinly served gap earns a lot).
    access_new = xp.exp(-dist / _D0_M).max(axis=1)
    gained = xp.maximum(0.0, access_new - access0)

    # Opportunity-weighted access (the O-D term) drives COVERAGE: a new on-ramp is
    # worth what it connects people to. `gained · reach` credits a stop for the
    # jobs/opportunities it unlocks, so a stop feeding a job-rich corridor beats an
    # equal-population stop on a dead-end. reach is a fixed per-cell weight in
    # [0,1] → saturation and monotonicity (greedy's submodular guarantee) hold.
    #
    # EQUITY stays pure need·pop·gained — "serve the underserved, including transit
    # deserts" — so it remains distinct from coverage and keeps favouring high-need
    # areas even where current job-access is low (the equity-vs-coverage tradeoff).
    opp_gained = gained * reach

    cov_val = float((pop * opp_gained).sum())
    eq_val = float((need * pop * gained).sum())

    nearest_any = xp.minimum(nearest0, dist.min(axis=1))
    burden_removed = float((pop * (nearest0 - nearest_any)).sum())
    return cov_val, eq_val, burden_removed


def _score_layout(
    stops: list[tuple[int, int]],
    spec: RewardSpec,
    feats: _GridFeatures,
    *,
    arrays: _LayoutArrays | None = None,
    xp=np,
) -> tuple[float, dict[str, float]]:
    """Return (R, channel_scores) for a layout. Pure; no I/O.

    Channels (each a "% of the budget-achievable best", in [0, 1]):
      coverage   — population given NEW access, weighted by opportunity reach (O-D)
      equity     — population given NEW access, weighted by need (low-income share)
      travel     — reduction in person-weighted walk burden
      constraint — feasibility: 1 − spacing penalty (new stops only)

    By default the per-cell features come from ``feats`` as host NumPy arrays (the
    path tests and one-off calls use — byte-identical CPU numerics). The greedy
    search passes pre-staged backend ``arrays`` + the matching ``xp`` so the hot
    loop runs GPU-resident on the Spark with no per-call host↔device copies.
    """
    total_w = (
        spec.coverage_weight
        + spec.travel_weight
        + spec.equity_weight
        + spec.constraint_weight
    )
    if total_w <= 0:
        return 0.0, {"coverage": 0.0, "equity": 0.0, "travel": 0.0, "constraint": 1.0}

    if not stops:
        # do-nothing baseline: zero gained access, zero burden reduction.
        return 0.0, {"coverage": 0.0, "equity": 0.0, "travel": 0.0, "constraint": 1.0}

    if arrays is None:
        arrays = (
            feats.demand_lon,
            feats.demand_lat,
            feats.pop,
            feats.need,
            feats.access0,
            feats.nearest0,
            feats.reach,
        )
    demand_lon, demand_lat, pop, need, access0, nearest0, reach = arrays

    slon = xp.asarray([_cell_to_lonlat(r, c)[0] for r, c in stops])
    slat = xp.asarray([_cell_to_lonlat(r, c)[1] for r, c in stops])
    cov_val, eq_val, burden_removed = _layout_terms(
        demand_lon, demand_lat, pop, need, access0, nearest0, reach, slon, slat, xp
    )

    budget = spec.budget

    # Each channel: % of what `budget` stops could best achieve.
    coverage = _ratio(cov_val, _ideal_b(feats.cov_cumsum, budget))
    equity = _ratio(eq_val, _ideal_b(feats.eq_cumsum, budget))
    travel = _ratio(burden_removed, _ideal_b(feats.travel_cumsum, budget))
    constraint = 1.0 - _spacing_penalty(stops)

    scores = {
        "coverage": coverage,
        "equity": equity,
        "travel": travel,
        "constraint": constraint,
    }
    r = (
        spec.coverage_weight * coverage
        + spec.travel_weight * travel
        + spec.equity_weight * equity
        + spec.constraint_weight * constraint
    ) / total_w
    return float(min(max(r, 0.0), 1.0)), scores


def _reward(
    stops: list[tuple[int, int]],
    spec: RewardSpec,
    feats: _GridFeatures | None = None,
) -> float:
    """Scalar reward for a layout. Pure when `feats` is supplied.

    `feats` defaults to the cached city-wide features for convenience (tests /
    one-off calls); the optimiser always passes a struct so no reload happens in
    the hot loop.
    """
    if feats is None:
        feats = _load_grid_features()
    return _score_layout(stops, spec, feats)[0]


# ---------------------------------------------------------------------------
# Greedy + local-search optimiser
# ---------------------------------------------------------------------------


def _stops_lonlat(cells: list[tuple[int, int]]) -> list[dict[str, float]]:
    out = []
    for r, c in cells:
        lon, lat = _cell_to_lonlat(r, c)
        out.append({"lon": float(lon), "lat": float(lat)})
    return out


def _greedy_search(
    spec: RewardSpec,
    seed: int,
    feats: _GridFeatures,
    candidates: tuple[tuple[int, int], ...] | None = None,
) -> tuple[list[tuple[int, int]], list[dict[str, Any]], str]:
    """Greedy-add (warm-started from the existing network via access0) then a
    local-search swap pass. Returns (placed_cells, per_step_states, stopped_reason).

    `candidates` overrides the cell set the search may place into (e.g. masked to a
    named region); defaults to the full city-wide candidate set in `feats`.

    Each step state is {stops: [{lon, lat}], R, channel_scores} so the frontend can
    animate the network being built and re-solve on weight change.
    """
    rng = random.Random(seed)
    cands = list(feats.candidates if candidates is None else candidates)
    rng.shuffle(cands)  # deterministic tie-break order

    # Resolve the array backend once. On a laptop this is NumPy and `arrays` stays
    # None → the exact CPU path. On the Spark it is CuPy: stage the per-cell features
    # onto the GPU a single time, then every score eval in the hot loop below reads
    # them with zero host↔device copies. The kernel (_layout_terms) is unchanged.
    backend = get_backend()
    xp = backend.xp
    arrays: _LayoutArrays | None = None
    if backend.is_gpu:
        arrays = (
            xp.asarray(feats.demand_lon),
            xp.asarray(feats.demand_lat),
            xp.asarray(feats.pop),
            xp.asarray(feats.need),
            xp.asarray(feats.access0),
            xp.asarray(feats.nearest0),
            xp.asarray(feats.reach),
        )

    placed: list[tuple[int, int]] = []
    cur_r, cur_scores = _score_layout(placed, spec, feats, arrays=arrays, xp=xp)
    steps: list[dict[str, Any]] = [
        {"stops": [], "R": cur_r, "channel_scores": cur_scores}
    ]
    stopped_reason = "budget"

    # --- Greedy-add phase ---
    while len(placed) < spec.budget:
        best_cell = None
        best_r = cur_r
        for cell in cands:
            if cell in placed:
                continue
            r, _ = _score_layout(placed + [cell], spec, feats, arrays=arrays, xp=xp)
            if r > best_r + _EPS:
                best_r = r
                best_cell = cell
        # A stop earns its place only if its marginal gain beats the per-stop cost.
        if best_cell is None or (best_r - cur_r) <= _LAMBDA_STOP_COST:
            stopped_reason = "diminishing_returns"
            break
        placed.append(best_cell)
        cur_r, cur_scores = _score_layout(placed, spec, feats, arrays=arrays, xp=xp)
        steps.append(
            {
                "stops": _stops_lonlat(placed),
                "R": cur_r,
                "channel_scores": cur_scores,
            }
        )

    # --- Local-search swap pass: relocate a placed stop if it strictly helps.
    for _ in range(3):  # bounded passes; R strictly increases per accepted swap
        improved = False
        for idx in range(len(placed)):
            best_swap = None
            best_r = cur_r
            for cell in cands:
                if cell in placed:
                    continue
                trial = placed.copy()
                trial[idx] = cell
                r, _ = _score_layout(trial, spec, feats, arrays=arrays, xp=xp)
                if r > best_r + _EPS:
                    best_r = r
                    best_swap = cell
            if best_swap is not None:
                placed[idx] = best_swap
                cur_r, cur_scores = _score_layout(
                    placed, spec, feats, arrays=arrays, xp=xp
                )
                steps.append(
                    {
                        "stops": _stops_lonlat(placed),
                        "R": cur_r,
                        "channel_scores": cur_scores,
                    }
                )
                improved = True
        if not improved:
            break

    return placed, steps, stopped_reason


def _greedy_place(
    spec: RewardSpec, seed: int = 42, feats: _GridFeatures | None = None
) -> list[tuple[int, int]]:
    """Greedy stop placement returning the placed candidate cells.

    The reward eval runs GPU-resident on the Spark (CuPy) via _greedy_search.
    # TODO(spark): add a cuOpt MILP exact baseline warm-started from this greedy
    #              solution at full Toronto resolution.
    """
    if feats is None:
        feats = _load_grid_features()
    placed, _steps, _reason = _greedy_search(spec, seed, feats)
    return placed


# ---------------------------------------------------------------------------
# Tool: parse_goal
# ---------------------------------------------------------------------------


class ParseGoalArgs(BaseModel):
    text: str = Field(
        ...,
        min_length=5,
        description="Plain-English goal from the planner, e.g. 'Improve access for low-income Scarborough without raising downtown commute times.'",
    )


@tool(ParseGoalArgs)
async def parse_goal(args: ParseGoalArgs) -> dict:
    """Translate a plain-English planning goal into a structured RewardSpec (weights, region, budget)."""
    client = get_nim_client()

    system_prompt = (
        # /no_think: Nemotron otherwise prepends its reasoning trace, breaking json.loads.
        "/no_think\n"
        "You are a transit-planning assistant. "
        "Given a plain-English goal from a city planner, extract a structured reward specification "
        "as a JSON object with these fields:\n"
        "  coverage_weight (float 0-1): importance of serving more people\n"
        "  travel_weight   (float 0-1): importance of reducing travel distance\n"
        "  equity_weight   (float 0-1): importance of serving underserved/low-income areas\n"
        "  constraint_weight (float 0-1): importance of feasibility constraints\n"
        "  region (string): the target area or neighbourhood name\n"
        "  budget (int > 0): number of new or relocated stops\n"
        "  protect (string | null): corridor/area to protect from worsening, or null\n\n"
        "Respond ONLY with the raw JSON object — no markdown fences, no commentary."
    )

    user_prompt = f"Goal: {args.text}"

    response = await client.chat(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    raw_content: str = response["choices"][0]["message"]["content"]

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        # Graceful degradation: return sensible defaults and flag the parse error
        return {
            "error": f"model returned non-JSON output: {exc}",
            "raw": raw_content,
            "reward_spec": RewardSpec(region="Toronto", budget=5).model_dump(),
        }

    try:
        spec = RewardSpec(**data)
    except Exception as exc:  # pydantic ValidationError or missing fields
        return {
            "error": f"reward spec validation failed: {exc}",
            "raw": raw_content,
            "reward_spec": RewardSpec(region="Toronto", budget=5).model_dump(),
        }

    return {"reward_spec": spec.model_dump(), "raw": raw_content}


# ---------------------------------------------------------------------------
# Tool: optimize_layout
# ---------------------------------------------------------------------------


class OptimizeLayoutArgs(BaseModel):
    reward_spec: dict = Field(
        ...,
        description="A RewardSpec dict (as returned by parse_goal) defining the optimisation objective",
    )
    seed: int = Field(42, ge=0, description="Random seed for reproducibility")
    max_iterations: int = Field(
        50,
        gt=0,
        le=5000,
        description="Maximum greedy/hill-climbing iterations (CPU fallback only)",
    )


@tool(OptimizeLayoutArgs)
def optimize_layout(args: OptimizeLayoutArgs) -> dict:
    """Discover the BEST stop layout for a goal the planner does NOT yet have a concrete plan for
    (e.g. "where should we add stops to help low-income areas"). Returns recommended stop
    locations, per-step states, and the metric trajectory.

    Use when the planner asks "what should we do" / "where should stops go" / "find the best ...".
    Do NOT use to evaluate a specific proposed change — that is simulate_change. Requires a reward
    spec from parse_goal.

    Greedy add (warm-started from the existing network) + local-search swap pass.
    May return fewer than `budget` stops when extra stops stop paying for
    themselves (per-stop cost). Deterministic given the seed.

    The reward eval is GPU-resident on the Spark (CuPy) and CPU-NumPy on a laptop —
    same kernel either way (see app/tools/_gpu.py, _layout_terms).
    """
    # TODO(spark): on top of the GPU reward eval, solve the exact MCLP with cuOpt
    #              warm-started from this greedy solution as an optimality baseline.

    try:
        spec = RewardSpec(**args.reward_spec)
    except Exception as exc:
        return {"error": f"invalid reward_spec: {exc}"}

    job_id = str(uuid.uuid4())
    start = time.time()

    feats = _load_grid_features()
    # Confine placement to the region the planner named, instead of scattering
    # stops across all of Toronto (the bug: "optimize York University Heights"
    # returned stops city-wide). Falls back to citywide if the name is unmatched
    # or finer than the candidate grid can resolve.
    region_cands, region_restricted = _region_candidates(
        spec.region, feats.candidates, min_count=spec.budget
    )
    placed, steps, stopped_reason = _greedy_search(
        spec, args.seed, feats, candidates=region_cands
    )

    final_reward = steps[-1]["R"]
    channel_scores = steps[-1]["channel_scores"]
    trajectory = [float(s["R"]) for s in steps]
    elapsed = time.time() - start

    stop_lonlats = [_cell_to_lonlat(r, c) for r, c in placed]

    result = {
        "job_id": job_id,
        "region": spec.region,
        "region_restricted": region_restricted,
        "candidate_count": len(region_cands),
        "budget": spec.budget,
        "stops": [{"lon": float(lon), "lat": float(lat)} for lon, lat in stop_lonlats],
        "stop_cells": [{"row": r, "col": c} for r, c in placed],
        "final_reward": float(final_reward),
        "channel_scores": channel_scores,
        "reward_trajectory": trajectory,
        "steps": steps,
        "stopped_reason": stopped_reason,
        "stop_cost": _LAMBDA_STOP_COST,
        "elapsed_s": float(round(elapsed, 3)),
        # Reward eval runs on whichever array backend resolved: "cpu_greedy" on a
        # laptop (NumPy), "gpu_greedy" on the Spark (CuPy). See app/tools/_gpu.py.
        "method": f"{get_backend().name}_greedy",
    }

    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "reward_trajectory": result["reward_trajectory"],
        "final_reward": final_reward,
        "channel_scores": channel_scores,
        "region": spec.region,
        "stops": result["stops"],
        "stopped_reason": stopped_reason,
        "elapsed_s": result["elapsed_s"],
    }

    return result


# ---------------------------------------------------------------------------
# Tool: propose_candidates
# ---------------------------------------------------------------------------


class ProposeCandidatesArgs(BaseModel):
    goal: str = Field(
        ...,
        min_length=5,
        description="Plain-English planning goal used to suggest candidate stop cells",
    )
    n: int = Field(5, gt=0, le=50, description="Number of candidate cells to propose")
    seed: int = Field(42, ge=0, description="Random seed for deterministic output")


@tool(ProposeCandidatesArgs)
async def propose_candidates(args: ProposeCandidatesArgs) -> dict:
    """Suggest N candidate stop-relocation cells to warm-start RL exploration, guided by Nemotron."""
    client = get_nim_client()

    system_prompt = (
        # /no_think so the model returns a clean JSON array, not a reasoning trace.
        "/no_think\n"
        "You are a transit-planning assistant. "
        "Given a planning goal, suggest candidate areas of the city to focus stop-placement on. "
        f"The city grid is {_GRID_ROWS} rows × {_GRID_COLS} cols. "
        "Row 0 is the northernmost row; col 0 is the westernmost column. "
        "Return ONLY a JSON array of objects with 'row' (int) and 'col' (int) fields, "
        f"with exactly {args.n} entries within bounds."
    )

    user_prompt = f"Goal: {args.goal}"

    response = await client.chat(messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    raw_content: str = response["choices"][0]["message"]["content"]

    candidates: list[dict] = []
    parse_error: str | None = None

    try:
        data = json.loads(raw_content)
        if not isinstance(data, list):
            raise ValueError("expected a JSON array")
        for item in data:
            row = int(item["row"])
            col = int(item["col"])
            if 0 <= row < _GRID_ROWS and 0 <= col < _GRID_COLS:
                lon, lat = _cell_to_lonlat(row, col)
                candidates.append({
                    "row": row,
                    "col": col,
                    "lon": float(lon),
                    "lat": float(lat),
                })
    except Exception as exc:
        parse_error = str(exc)
        # Fall back to greedy-seeded candidates
        rng = random.Random(args.seed)
        cells = _grid_cells()
        rng.shuffle(cells)
        for row, col in cells[: args.n]:
            lon, lat = _cell_to_lonlat(row, col)
            candidates.append({
                "row": row,
                "col": col,
                "lon": float(lon),
                "lat": float(lat),
            })

    result: dict[str, Any] = {"candidates": candidates[: args.n]}
    if parse_error is not None:
        result["parse_error"] = parse_error
        result["fallback"] = True

    return result


# ---------------------------------------------------------------------------
# Tool: optimization_status
# ---------------------------------------------------------------------------


class OptimizationStatusArgs(BaseModel):
    job_id: str = Field(..., min_length=1, description="Job ID returned by optimize_layout")


@tool(OptimizationStatusArgs)
def optimization_status(args: OptimizationStatusArgs) -> dict:
    """Return the live metric trajectory and status for an optimization job."""
    if args.job_id not in _JOBS:
        return {
            "job_id": args.job_id,
            "status": "not_found",
            "error": f"No job with id {args.job_id!r} found.",
            "reward_trajectory": [],
        }

    job = _JOBS[args.job_id]
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "reward_trajectory": job["reward_trajectory"],
        "final_reward": job.get("final_reward"),
        "channel_scores": job.get("channel_scores"),
        "region": job.get("region"),
        "stops": job.get("stops", []),
        "stopped_reason": job.get("stopped_reason"),
        "elapsed_s": job.get("elapsed_s"),
    }
