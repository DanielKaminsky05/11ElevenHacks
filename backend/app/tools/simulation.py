"""TransitRL tools — Family C: Scenario Simulation.

Tools that test a hypothesis: simulate_change, diff_scenarios, constraint_check.
Register each with `@tool` from app.tools.registry.

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

import math
import warnings
from functools import lru_cache
from typing import Annotated, Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import unary_union

from app.data import resolve
from app.tools.registry import tool

# ---------------------------------------------------------------------------
# Toronto bounding box (loose) – used for "outside Toronto" guard
# ---------------------------------------------------------------------------
_TORONTO_BBOX = {
    "min_lon": -79.70,
    "max_lon": -79.10,
    "min_lat": 43.55,
    "max_lat": 43.95,
}

# Default walk-buffer radius used for accessibility calculations
_DEFAULT_BUFFER_M = 400

# Approximate metres per degree of latitude and longitude at Toronto's latitude
_M_PER_DEG_LAT = 111_139.0
_M_PER_DEG_LON = 111_139.0 * math.cos(math.radians(43.7))


# ---------------------------------------------------------------------------
# Shared Pydantic sub-models
# ---------------------------------------------------------------------------


class StopCoord(BaseModel):
    """A lat/lon coordinate for a transit stop."""

    lon: float = Field(..., ge=-180, le=180, description="Longitude (WGS-84)")
    lat: float = Field(..., ge=-90, le=90, description="Latitude (WGS-84)")


class AddStopOp(BaseModel):
    op: Literal["add_stop"]
    stop_id: str = Field(..., min_length=1, description="Unique ID for the new stop")
    coord: StopCoord


class MoveStopOp(BaseModel):
    op: Literal["move_stop"]
    stop_id: str = Field(..., min_length=1, description="ID of the stop to move")
    new_coord: StopCoord


class RemoveStopOp(BaseModel):
    op: Literal["remove_stop"]
    stop_id: str = Field(..., min_length=1, description="ID of the stop to remove")


# Discriminated union of operations
StopOperation = Annotated[
    AddStopOp | MoveStopOp | RemoveStopOp,
    Field(discriminator="op"),
]


# ---------------------------------------------------------------------------
# Private data-loading helpers (cached)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_gtfs_stops() -> gpd.GeoDataFrame:
    """Load TTC GTFS stops as a GeoDataFrame (EPSG:4326)."""
    path = resolve("transit", "ttc-routes-schedules-gtfs", "stops.txt")
    df = pd.read_csv(path, usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
    df["stop_id"] = df["stop_id"].astype(str)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["stop_lon"], df["stop_lat"]),
        crs="EPSG:4326",
    )
    return gdf


@lru_cache(maxsize=1)
def _load_neighbourhoods() -> gpd.GeoDataFrame:
    """Load Neighbourhoods-158 as a GeoDataFrame (EPSG:4326)."""
    path = resolve("geospatial", "neighbourhoods-158.geojson")
    gdf = gpd.read_file(path)
    return gdf


@lru_cache(maxsize=1)
def _load_neighbourhood_profiles() -> pd.DataFrame:
    """Load neighbourhood profiles: population and low-income prevalence per neighbourhood."""
    path = resolve("census-demographics", "neighbourhood-profiles-2021.xlsx")
    df = pd.read_excel(path, header=None)

    # Row 0: neighbourhood names, row 1: neighbourhood numbers (1–158)
    names = df.iloc[0, 1:].tolist()
    numbers = df.iloc[1, 1:].tolist()

    # Row 3: total population (25% sample)
    pop_values = df.iloc[3, 1:].tolist()

    # Row 178: prevalence of low income (LIM-AT) %
    low_income_pct_values = df.iloc[178, 1:].tolist()

    profiles = pd.DataFrame(
        {
            "neighbourhood_name": names,
            "neighbourhood_number": pd.to_numeric(
                pd.Series(numbers), errors="coerce"
            ),
            "population": pd.to_numeric(
                pd.Series(pop_values), errors="coerce"
            ).fillna(0),
            "low_income_pct": pd.to_numeric(
                pd.Series(low_income_pct_values), errors="coerce"
            ).fillna(0),
        }
    )
    return profiles


@lru_cache(maxsize=2)
def _load_route_shapes(gtfs_folder: str) -> MultiLineString:
    """Load GTFS shapes.txt for a given folder name and return a merged MultiLineString."""
    path = resolve("transit", gtfs_folder, "shapes.txt")
    df = pd.read_csv(path, usecols=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])
    df = df.sort_values(["shape_id", "shape_pt_sequence"])

    lines = []
    for _, grp in df.groupby("shape_id"):
        coords = list(zip(grp["shape_pt_lon"], grp["shape_pt_lat"]))
        if len(coords) >= 2:
            lines.append(LineString(coords))

    if not lines:
        return MultiLineString()
    return MultiLineString(lines)


# ---------------------------------------------------------------------------
# Private accessibility engine
# ---------------------------------------------------------------------------
# TODO: replace this self-contained helper with Family B's compute_accessibility
# engine once that module is stable. For now we implement a lightweight walk-buffer
# accessibility metric using only geopandas / shapely so the tests can run on CPU.


def _compute_accessibility_metrics(
    stops_gdf: gpd.GeoDataFrame,
    buffer_m: float = _DEFAULT_BUFFER_M,
) -> dict:
    """Compute walk-buffer accessibility for a given set of stops.

    Returns a dict with:
      - pct_covered: fraction of neighbourhoods (by population) within *buffer_m*
        of at least one stop (float in [0, 1]).
      - mean_distance_m: population-weighted mean distance to the nearest stop (float).
      - equity_weighted_access: access weighted by (1 - low_income_pct) inverse;
        higher means better access in low-income areas (float in [0, 1]).
      - neighbourhood_access: list of dicts per neighbourhood with coverage flag.
    """
    neighbourhoods = _load_neighbourhoods()
    profiles = _load_neighbourhood_profiles()

    # Merge population/income into neighbourhood geodataframe
    # AREA_SHORT_CODE is a string like "1"; neighbourhood_number is int64 — align types
    profiles_str = profiles.copy()
    profiles_str["neighbourhood_number_str"] = profiles_str["neighbourhood_number"].astype(str).str.strip()
    nbhd = neighbourhoods.merge(
        profiles_str,
        left_on="AREA_SHORT_CODE",
        right_on="neighbourhood_number_str",
        how="left",
    )
    # Fallback: try string match on AREA_NAME if numeric merge yields NaN
    unmatched_mask = nbhd["population"].isna()
    if unmatched_mask.any():
        name_map = profiles.set_index("neighbourhood_name")[["population", "low_income_pct"]]
        for idx in nbhd[unmatched_mask].index:
            nm = nbhd.at[idx, "AREA_NAME"]
            if nm in name_map.index:
                nbhd.at[idx, "population"] = name_map.at[nm, "population"]
                nbhd.at[idx, "low_income_pct"] = name_map.at[nm, "low_income_pct"]
    nbhd["population"] = pd.to_numeric(nbhd["population"], errors="coerce").fillna(0)
    nbhd["low_income_pct"] = pd.to_numeric(nbhd["low_income_pct"], errors="coerce").fillna(0)

    # Centroid of each neighbourhood in EPSG:4326
    nbhd = nbhd.copy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        nbhd["centroid"] = nbhd.geometry.centroid

    if stops_gdf.empty:
        # No stops → no coverage
        nbhd_access = [
            {
                "neighbourhood_name": str(row["AREA_NAME"]),
                "covered": False,
                "nearest_stop_m": None,
                "population": float(row["population"]),
                "low_income_pct": float(row["low_income_pct"]),
            }
            for _, row in nbhd.iterrows()
        ]
        return {
            "pct_covered": 0.0,
            "mean_distance_m": None,
            "equity_weighted_access": 0.0,
            "neighbourhood_access": nbhd_access,
        }

    # Convert buffer from metres to approximate degrees (latitude-based)
    buffer_deg = buffer_m / _M_PER_DEG_LAT

    # Build union of all stop buffers
    stop_buffer_union = unary_union([geom.buffer(buffer_deg) for geom in stops_gdf.geometry])

    nbhd_access = []
    total_pop = 0.0
    covered_pop = 0.0
    weighted_dist_sum = 0.0
    equity_num = 0.0
    equity_denom = 0.0

    for _, row in nbhd.iterrows():
        centroid = row["centroid"]
        pop = float(row["population"])
        li_pct = float(row["low_income_pct"]) / 100.0  # convert % to fraction

        # Nearest stop distance in metres
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            dists = stops_gdf.geometry.distance(centroid) * _M_PER_DEG_LAT
        nearest_m = float(dists.min())

        covered = stop_buffer_union.contains(centroid)

        total_pop += pop
        if covered:
            covered_pop += pop
            weighted_dist_sum += nearest_m * pop
        else:
            weighted_dist_sum += nearest_m * pop  # still contributes to mean

        # Equity weight: neighbourhoods with higher low-income share get extra weight
        equity_weight = 1.0 + li_pct  # range [1.0, 2.0]
        equity_denom += pop * equity_weight
        if covered:
            equity_num += pop * equity_weight

        nbhd_access.append(
            {
                "neighbourhood_name": str(row["AREA_NAME"]),
                "covered": bool(covered),
                "nearest_stop_m": round(nearest_m, 1),
                "population": float(pop),
                "low_income_pct": float(row["low_income_pct"]),
            }
        )

    pct_covered = covered_pop / total_pop if total_pop > 0 else 0.0
    mean_distance_m = weighted_dist_sum / total_pop if total_pop > 0 else None
    equity_weighted_access = equity_num / equity_denom if equity_denom > 0 else 0.0

    return {
        "pct_covered": round(float(pct_covered), 4),
        "mean_distance_m": round(float(mean_distance_m), 1) if mean_distance_m is not None else None,
        "equity_weighted_access": round(float(equity_weighted_access), 4),
        "neighbourhood_access": nbhd_access,
    }


def _apply_operations(
    stops_gdf: gpd.GeoDataFrame,
    operations: list[StopOperation],
) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Apply a list of add/move/remove operations to a stops GeoDataFrame.

    Returns (modified_gdf, list_of_warnings).
    Warnings are issued (not errors) for non-fatal problems like removing a
    non-existent stop.
    """
    gdf = stops_gdf.copy()
    warnings: list[str] = []

    for op in operations:
        if isinstance(op, AddStopOp):
            new_row = pd.DataFrame(
                {
                    "stop_id": [op.stop_id],
                    "stop_name": [f"Added stop {op.stop_id}"],
                    "stop_lat": [op.coord.lat],
                    "stop_lon": [op.coord.lon],
                    "geometry": [Point(op.coord.lon, op.coord.lat)],
                }
            )
            new_gdf = gpd.GeoDataFrame(new_row, crs="EPSG:4326")
            gdf = pd.concat([gdf, new_gdf], ignore_index=True)

        elif isinstance(op, MoveStopOp):
            mask = gdf["stop_id"] == op.stop_id
            if not mask.any():
                warnings.append(f"move_stop: stop_id '{op.stop_id}' not found; skipped")
                continue
            gdf.loc[mask, "stop_lat"] = op.new_coord.lat
            gdf.loc[mask, "stop_lon"] = op.new_coord.lon
            gdf.loc[mask, "geometry"] = Point(op.new_coord.lon, op.new_coord.lat)

        elif isinstance(op, RemoveStopOp):
            mask = gdf["stop_id"] == op.stop_id
            if not mask.any():
                warnings.append(f"remove_stop: stop_id '{op.stop_id}' not found; skipped")
                continue
            gdf = gdf[~mask].reset_index(drop=True)

    return gdf, warnings


def _winners_losers(
    before_access: list[dict],
    after_access: list[dict],
) -> dict:
    """Classify neighbourhoods as winners, losers, or unchanged based on coverage change."""
    before_map = {r["neighbourhood_name"]: r for r in before_access}
    after_map = {r["neighbourhood_name"]: r for r in after_access}

    winners = []
    losers = []
    unchanged = []

    all_names = set(before_map) | set(after_map)
    for name in all_names:
        bef = before_map.get(name)
        aft = after_map.get(name)
        if bef is None or aft is None:
            continue

        bef_dist = bef.get("nearest_stop_m") or 0.0
        aft_dist = aft.get("nearest_stop_m") or 0.0
        delta_m = aft_dist - bef_dist  # negative = improvement (closer stop)

        entry = {
            "neighbourhood_name": name,
            "population": bef["population"],
            "low_income_pct": bef["low_income_pct"],
            "before_covered": bef["covered"],
            "after_covered": aft["covered"],
            "delta_nearest_stop_m": round(delta_m, 1),
        }

        if delta_m < -10:
            winners.append(entry)
        elif delta_m > 10:
            losers.append(entry)
        else:
            unchanged.append(entry)

    winners.sort(key=lambda x: x["delta_nearest_stop_m"])
    losers.sort(key=lambda x: x["delta_nearest_stop_m"], reverse=True)

    return {
        "winners": winners,
        "losers": losers,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# Tool 1: simulate_change
# ---------------------------------------------------------------------------


class SimulateChangeArgs(BaseModel):
    """Arguments for simulate_change."""

    operations: list[StopOperation] = Field(
        default_factory=list,
        description="List of stop operations (add_stop / move_stop / remove_stop) to apply",
    )
    buffer_m: float = Field(
        _DEFAULT_BUFFER_M,
        gt=0,
        le=2000,
        description="Walk-buffer radius in metres for coverage calculation",
    )


@tool(SimulateChangeArgs)
def simulate_change(args: SimulateChangeArgs) -> dict:
    """Predict the effect of a SPECIFIC, user-proposed change (e.g. "add stops on Finch",
    "remove the King St stop"). Takes explicit add/move/remove operations; returns before/after
    accessibility metrics and a winners/losers breakdown.

    Use when the planner already has a change in mind ("what if ...", "what happens if we ...").
    Do NOT use to discover the best change — that is optimize_layout. Do NOT use for current
    state with no change — that is compute_accessibility / list_transit."""
    baseline_stops = _load_gtfs_stops()

    # Before metrics
    before_metrics = _compute_accessibility_metrics(baseline_stops, buffer_m=args.buffer_m)

    # Apply operations
    after_stops, warnings = _apply_operations(baseline_stops, args.operations)

    # After metrics
    after_metrics = _compute_accessibility_metrics(after_stops, buffer_m=args.buffer_m)

    # Winners / losers
    breakdown = _winners_losers(
        before_metrics["neighbourhood_access"],
        after_metrics["neighbourhood_access"],
    )

    # Travel-time proxy: use mean_distance_m as a proxy (seconds assuming 1.2 m/s walk speed)
    def dist_to_time(d: float | None) -> float | None:
        if d is None:
            return None
        return round(d / 1.2, 1)  # seconds

    return {
        "before": {
            "stop_count": int(len(baseline_stops)),
            "pct_covered": before_metrics["pct_covered"],
            "mean_walk_distance_m": before_metrics["mean_distance_m"],
            "mean_walk_time_s": dist_to_time(before_metrics["mean_distance_m"]),
            "equity_weighted_access": before_metrics["equity_weighted_access"],
        },
        "after": {
            "stop_count": int(len(after_stops)),
            "pct_covered": after_metrics["pct_covered"],
            "mean_walk_distance_m": after_metrics["mean_distance_m"],
            "mean_walk_time_s": dist_to_time(after_metrics["mean_distance_m"]),
            "equity_weighted_access": after_metrics["equity_weighted_access"],
        },
        "delta": {
            "pct_covered": round(
                after_metrics["pct_covered"] - before_metrics["pct_covered"], 4
            ),
            "mean_walk_distance_m": (
                round(
                    (after_metrics["mean_distance_m"] or 0.0)
                    - (before_metrics["mean_distance_m"] or 0.0),
                    1,
                )
                if before_metrics["mean_distance_m"] is not None
                else None
            ),
            "equity_weighted_access": round(
                after_metrics["equity_weighted_access"]
                - before_metrics["equity_weighted_access"],
                4,
            ),
        },
        "winners_losers": breakdown,
        "warnings": warnings,
        "ops_applied": len(args.operations),
    }


# ---------------------------------------------------------------------------
# Tool 2: diff_scenarios
# ---------------------------------------------------------------------------


class ScenarioLayout(BaseModel):
    """A transit stop layout: a list of stops with coordinates."""

    stops: list[dict] = Field(
        ...,
        description=(
            "List of stops, each with keys: stop_id (str), lat (float), lon (float). "
            "Use the baseline GTFS layout or a custom list."
        ),
        min_length=0,
    )
    label: str = Field("unnamed", description="Human-readable label for this layout")

    @model_validator(mode="after")
    def validate_stops(self) -> "ScenarioLayout":
        for s in self.stops:
            if not isinstance(s, dict):
                raise ValueError("Each stop must be a dict")
            for key in ("stop_id", "lat", "lon"):
                if key not in s:
                    raise ValueError(f"Stop missing required key: {key!r}")
        return self


class DiffScenariosArgs(BaseModel):
    """Arguments for diff_scenarios."""

    scenario_a: ScenarioLayout = Field(..., description="First layout (typically the baseline)")
    scenario_b: ScenarioLayout = Field(..., description="Second layout to compare against A")
    buffer_m: float = Field(
        _DEFAULT_BUFFER_M,
        gt=0,
        le=2000,
        description="Walk-buffer radius in metres for coverage calculation",
    )


def _layout_to_gdf(layout: ScenarioLayout) -> gpd.GeoDataFrame:
    """Convert a ScenarioLayout to a GeoDataFrame."""
    if not layout.stops:
        return gpd.GeoDataFrame(
            columns=["stop_id", "stop_lat", "stop_lon", "geometry"],
            geometry="geometry",
            crs="EPSG:4326",
        )
    rows = [
        {
            "stop_id": str(s["stop_id"]),
            "stop_lat": float(s["lat"]),
            "stop_lon": float(s["lon"]),
        }
        for s in layout.stops
    ]
    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["stop_lon"], df["stop_lat"]),
        crs="EPSG:4326",
    )


@tool(DiffScenariosArgs)
def diff_scenarios(args: DiffScenariosArgs) -> dict:
    """Compare two stop layouts (A vs B) and return tabular accessibility deltas and per-neighbourhood diffs."""
    gdf_a = _layout_to_gdf(args.scenario_a)
    gdf_b = _layout_to_gdf(args.scenario_b)

    metrics_a = _compute_accessibility_metrics(gdf_a, buffer_m=args.buffer_m)
    metrics_b = _compute_accessibility_metrics(gdf_b, buffer_m=args.buffer_m)

    breakdown = _winners_losers(
        metrics_a["neighbourhood_access"],
        metrics_b["neighbourhood_access"],
    )

    # Stops added/removed
    ids_a = {str(s["stop_id"]) for s in args.scenario_a.stops}
    ids_b = {str(s["stop_id"]) for s in args.scenario_b.stops}

    return {
        "scenario_a": {
            "label": args.scenario_a.label,
            "stop_count": len(args.scenario_a.stops),
            "pct_covered": metrics_a["pct_covered"],
            "mean_walk_distance_m": metrics_a["mean_distance_m"],
            "equity_weighted_access": metrics_a["equity_weighted_access"],
        },
        "scenario_b": {
            "label": args.scenario_b.label,
            "stop_count": len(args.scenario_b.stops),
            "pct_covered": metrics_b["pct_covered"],
            "mean_walk_distance_m": metrics_b["mean_distance_m"],
            "equity_weighted_access": metrics_b["equity_weighted_access"],
        },
        "delta": {
            "pct_covered": round(metrics_b["pct_covered"] - metrics_a["pct_covered"], 4),
            "mean_walk_distance_m": (
                round(
                    (metrics_b["mean_distance_m"] or 0.0)
                    - (metrics_a["mean_distance_m"] or 0.0),
                    1,
                )
                if metrics_a["mean_distance_m"] is not None
                else None
            ),
            "equity_weighted_access": round(
                metrics_b["equity_weighted_access"] - metrics_a["equity_weighted_access"], 4
            ),
            "stops_added": sorted(ids_b - ids_a),
            "stops_removed": sorted(ids_a - ids_b),
        },
        "winners_losers": breakdown,
    }


# ---------------------------------------------------------------------------
# Tool 3: constraint_check
# ---------------------------------------------------------------------------

# Toronto bounding box polygon (used for "inside city" check)
_TORONTO_MIN_STOP_SPACING_M = 150.0  # hard lower bound on stop-to-stop distance


class StopLayoutForConstraint(BaseModel):
    """A layout of stops to check for feasibility constraints."""

    stops: list[dict] = Field(
        ...,
        description="List of stops, each with keys: stop_id (str), lat (float), lon (float)",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_stops(self) -> "StopLayoutForConstraint":
        for s in self.stops:
            if not isinstance(s, dict):
                raise ValueError("Each stop must be a dict")
            for key in ("stop_id", "lat", "lon"):
                if key not in s:
                    raise ValueError(f"Stop missing required key: {key!r}")
        return self


class ConstraintCheckArgs(BaseModel):
    """Arguments for constraint_check."""

    layout: StopLayoutForConstraint = Field(
        ..., description="The stop layout to validate"
    )
    min_spacing_m: float = Field(
        _TORONTO_MIN_STOP_SPACING_M,
        gt=0,
        le=5000,
        description="Minimum allowed distance between any two stops in metres",
    )
    max_route_distance_m: float = Field(
        500.0,
        gt=0,
        le=5000,
        description=(
            "Maximum allowed distance from a stop to the nearest GTFS route line in metres. "
            "Stops farther than this are flagged as 'not near a route'."
        ),
    )
    stop_budget: int = Field(
        9999,
        gt=0,
        description="Maximum number of stops allowed in the layout",
    )
    check_toronto_boundary: bool = Field(
        True,
        description="Flag stops that fall outside the Toronto bounding box",
    )


def _stops_to_points(layout: StopLayoutForConstraint) -> list[tuple[str, float, float]]:
    """Return list of (stop_id, lat, lon)."""
    return [(str(s["stop_id"]), float(s["lat"]), float(s["lon"])) for s in layout.stops]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@tool(ConstraintCheckArgs)
def constraint_check(args: ConstraintCheckArgs) -> dict:
    """Check a stop layout for feasibility: spacing, route proximity, stop budget, and Toronto boundary."""
    stops = _stops_to_points(args.layout)
    violations: list[dict] = []
    stop_results: list[dict] = []

    # 1. Stop budget
    budget_ok = len(stops) <= args.stop_budget
    if not budget_ok:
        violations.append(
            {
                "type": "stop_budget_exceeded",
                "message": (
                    f"Layout has {len(stops)} stops but budget is {args.stop_budget}"
                ),
                "stop_id": None,
            }
        )

    # 2. Load route shapes for proximity check (TTC GTFS)
    try:
        route_shapes = _load_route_shapes("ttc-routes-schedules-gtfs")
        route_shapes_available = True
    except FileNotFoundError:
        route_shapes = None
        route_shapes_available = False

    # 3. Per-stop checks
    for sid, lat, lon in stops:
        pt = Point(lon, lat)
        issues: list[str] = []

        # Toronto boundary
        if args.check_toronto_boundary:
            outside = (
                lon < _TORONTO_BBOX["min_lon"]
                or lon > _TORONTO_BBOX["max_lon"]
                or lat < _TORONTO_BBOX["min_lat"]
                or lat > _TORONTO_BBOX["max_lat"]
            )
            if outside:
                issues.append("outside_toronto_boundary")
                violations.append(
                    {
                        "type": "outside_toronto_boundary",
                        "message": f"Stop '{sid}' at ({lat:.4f}, {lon:.4f}) is outside Toronto",
                        "stop_id": sid,
                    }
                )

        # Route proximity
        route_dist_m: float | None = None
        if route_shapes_available and route_shapes is not None:
            # Convert approx metres to degrees for shapely distance
            dist_deg = route_shapes.distance(pt)
            route_dist_m = round(dist_deg * _M_PER_DEG_LAT, 1)
            if route_dist_m > args.max_route_distance_m:
                issues.append("far_from_route")
                violations.append(
                    {
                        "type": "far_from_route",
                        "message": (
                            f"Stop '{sid}' is {route_dist_m:.0f} m from nearest route "
                            f"(max {args.max_route_distance_m:.0f} m)"
                        ),
                        "stop_id": sid,
                    }
                )

        stop_results.append(
            {
                "stop_id": sid,
                "lat": lat,
                "lon": lon,
                "issues": issues,
                "route_dist_m": route_dist_m,
            }
        )

    # 4. Minimum spacing check (O(n²) — acceptable for ≤ a few thousand stops)
    spacing_violations: list[dict] = []
    for i in range(len(stops)):
        for j in range(i + 1, len(stops)):
            sid_i, lat_i, lon_i = stops[i]
            sid_j, lat_j, lon_j = stops[j]
            dist_m = _haversine_m(lat_i, lon_i, lat_j, lon_j)
            if dist_m < args.min_spacing_m:
                spacing_violations.append(
                    {
                        "type": "stops_too_close",
                        "message": (
                            f"Stops '{sid_i}' and '{sid_j}' are {dist_m:.0f} m apart "
                            f"(min {args.min_spacing_m:.0f} m)"
                        ),
                        "stop_id": sid_i,
                        "stop_id_b": sid_j,
                        "distance_m": round(dist_m, 1),
                    }
                )

    violations.extend(spacing_violations)

    feasible = len(violations) == 0

    return {
        "feasible": feasible,
        "stop_count": len(stops),
        "budget_ok": budget_ok,
        "route_shapes_available": route_shapes_available,
        "violations": violations,
        "violation_count": len(violations),
        "stops": stop_results,
    }
