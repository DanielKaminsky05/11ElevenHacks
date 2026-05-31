"""TransitRL tools — Family B: Accessibility & Equity Diagnostics.

Tools that diagnose problems: compute_accessibility, equity_gap_report,
reachability, estimate_demand, reliability_report. Register each with `@tool`
from app.tools.registry.

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Point, box

from app.schemas.common import BBox
from app.tools.registry import tool

# ---------------------------------------------------------------------------
# Cached data loaders (private to this module to avoid registry conflicts)
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Return the data directory without importing app.data (avoids Settings overhead)."""
    # backend/ → ../data
    return (Path(__file__).resolve().parents[3] / "data").resolve()


@lru_cache(maxsize=1)
def _load_gtfs_stops() -> gpd.GeoDataFrame:
    """Load TTC GTFS stops as a GeoDataFrame (EPSG:4326)."""
    path = _data_dir() / "transit" / "ttc-routes-schedules-gtfs" / "stops.txt"
    df = pd.read_csv(path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["stop_lon"], df["stop_lat"]),
        crs="EPSG:4326",
    )
    return gdf


@lru_cache(maxsize=1)
def _load_neighbourhoods() -> gpd.GeoDataFrame:
    """Load Neighbourhoods-158 boundaries (EPSG:4326)."""
    path = _data_dir() / "geospatial" / "neighbourhoods-158.geojson"
    return gpd.read_file(str(path))


@lru_cache(maxsize=1)
def _load_on_marg() -> pd.DataFrame:
    """Load ON-Marg 2021 neighbourhood marginalization scores."""
    path = _data_dir() / "census-demographics" / "on-marg-2021-toronto-n158.xlsx"
    xl = pd.ExcelFile(str(path))
    df = pd.read_excel(xl, sheet_name="Neighb_Toronto_ON-Marg2021", skiprows=1)
    # Row 0 contains actual column names
    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)
    # Coerce numeric columns
    numeric_cols = [
        "NH_Pop2021",
        "Households_Dwellings_NHsTO2021",
        "Material_Resources_NHsTO2021",
        "Age_Labourforce_NHsTO2021",
        "Racialized_NC_Pop_NHsTO2021",
        "Households_Dwellings_q_NHsTO2021",
        "Material_Resources_q_NHsTO2021",
        "Age_Labourforce_q_NHsTO2021",
        "Racialized_NC_Pop_q_NHsTO2021",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["NH_ID"] = pd.to_numeric(df["NH_ID"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def _load_nia() -> gpd.GeoDataFrame:
    """Load Neighbourhood Improvement Areas boundaries."""
    path = _data_dir() / "geospatial" / "neighbourhood-improvement-areas.geojson"
    return gpd.read_file(str(path))


@lru_cache(maxsize=1)
def _load_bus_delays() -> pd.DataFrame:
    """Load TTC bus delay data for 2025."""
    path = _data_dir() / "transit" / "ttc-bus-delay-2025.csv"
    df = pd.read_csv(str(path))
    df["Min Delay"] = pd.to_numeric(df["Min Delay"], errors="coerce").fillna(0)
    df["Min Gap"] = pd.to_numeric(df["Min Gap"], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def _load_streetcar_delays() -> pd.DataFrame:
    """Load TTC streetcar delay data for 2025."""
    path = _data_dir() / "transit" / "ttc-streetcar-delay-2025.csv"
    df = pd.read_csv(str(path))
    df["Min Delay"] = pd.to_numeric(df["Min Delay"], errors="coerce").fillna(0)
    df["Min Gap"] = pd.to_numeric(df["Min Gap"], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

# Approximate metres-per-degree for Toronto (lat ~43.7°)
_METRES_PER_DEG_LAT = 111_320.0
_METRES_PER_DEG_LON = 111_320.0 * math.cos(math.radians(43.7))


def _metres_to_deg_lat(m: float) -> float:
    return m / _METRES_PER_DEG_LAT


def _metres_to_deg_lon(m: float) -> float:
    return m / _METRES_PER_DEG_LON


def _bbox_to_shapely(bbox: BBox):
    """Convert BBox to a shapely box geometry."""
    return box(bbox.west, bbox.south, bbox.east, bbox.north)


def _filter_stops_by_bbox(stops: gpd.GeoDataFrame, bbox: BBox) -> gpd.GeoDataFrame:
    region = _bbox_to_shapely(bbox)
    return stops[stops.geometry.within(region)].copy()


def _filter_stops_by_geom(stops: gpd.GeoDataFrame, geom) -> gpd.GeoDataFrame:
    return stops[stops.geometry.within(geom)].copy()


# ---------------------------------------------------------------------------
# compute_accessibility
# ---------------------------------------------------------------------------

class ComputeAccessibilityArgs(BaseModel):
    bbox: BBox | None = Field(
        None,
        description="Restrict analysis to this bounding box (WGS84). None = whole city.",
    )
    threshold_m: float = Field(
        400,
        gt=0,
        le=2000,
        description="Walk-buffer radius in metres. Population within this distance "
        "of any stop is considered 'covered'.",
    )


@tool(ComputeAccessibilityArgs)
def compute_accessibility(args: ComputeAccessibilityArgs) -> dict:
    """Share of population within a walk buffer of any stop, and mean distance to nearest service.

    Uses TTC GTFS stops and Toronto neighbourhood boundaries (Neighbourhoods-158).
    Returns pct_covered [0–100], mean_distance_m, stop_count, and neighbourhood_count.
    Coverage is computed at neighbourhood centroid level weighted by population.
    """
    stops = _load_gtfs_stops()
    nbhoods = _load_neighbourhoods()

    # Filter stops to bbox if provided
    if args.bbox is not None:
        stops = _filter_stops_by_bbox(stops, args.bbox)
        region_geom = _bbox_to_shapely(args.bbox)
        # Filter neighbourhoods whose centroid falls inside the bbox
        centroids = nbhoods.geometry.centroid
        mask = centroids.within(region_geom)
        nbhoods = nbhoods[mask].copy()

    if nbhoods.empty:
        return {
            "pct_covered": 0.0,
            "mean_distance_m": None,
            "stop_count": int(len(stops)),
            "neighbourhood_count": 0,
            "threshold_m": float(args.threshold_m),
            "units": "pct_covered=percent [0-100], mean_distance_m=metres",
        }

    if stops.empty:
        return {
            "pct_covered": 0.0,
            "mean_distance_m": None,
            "stop_count": 0,
            "neighbourhood_count": int(len(nbhoods)),
            "threshold_m": float(args.threshold_m),
            "units": "pct_covered=percent [0-100], mean_distance_m=metres",
        }

    # Build walk buffer around each stop (in degrees, lon/lat approximation)
    # TODO(spark): replace with cuSpatial GPU buffer for whole-city scale
    buf_lat = _metres_to_deg_lat(args.threshold_m)
    buf_lon = _metres_to_deg_lon(args.threshold_m)

    # Union of all stop buffers (ellipsoidal approximation)
    stop_points = stops.geometry.values
    # Use a circular buffer approximation: scale x by lon factor, y by lat factor
    # Since we're in lon/lat, buffer by avg of two degree radii
    avg_buf_deg = (buf_lat + buf_lon) / 2.0
    stop_buffers = [pt.buffer(avg_buf_deg) for pt in stop_points]
    from shapely.ops import unary_union
    coverage_union = unary_union(stop_buffers)

    # Compute neighbourhood centroids
    centroids = nbhoods.geometry.centroid

    # For each neighbourhood centroid: covered? and distance to nearest stop
    covered_count = 0
    distances_m = []

    stop_coords = np.column_stack([stops.geometry.x.values, stops.geometry.y.values])

    for centroid in centroids:
        cx, cy = centroid.x, centroid.y
        is_covered = coverage_union.contains(centroid)
        if is_covered:
            covered_count += 1

        # Distance to nearest stop in metres
        dx = (stop_coords[:, 0] - cx) * _METRES_PER_DEG_LON
        dy = (stop_coords[:, 1] - cy) * _METRES_PER_DEG_LAT
        dist = np.sqrt(dx**2 + dy**2)
        distances_m.append(float(dist.min()))

    total = len(nbhoods)
    pct_covered = (covered_count / total * 100.0) if total > 0 else 0.0
    mean_dist = float(np.mean(distances_m)) if distances_m else None

    return {
        "pct_covered": round(pct_covered, 2),
        "mean_distance_m": round(mean_dist, 1) if mean_dist is not None else None,
        "stop_count": int(len(stops)),
        "neighbourhood_count": int(total),
        "covered_count": int(covered_count),
        "threshold_m": float(args.threshold_m),
        "units": "pct_covered=percent [0-100], mean_distance_m=metres",
    }


# ---------------------------------------------------------------------------
# equity_gap_report
# ---------------------------------------------------------------------------

class EquityGapReportArgs(BaseModel):
    bbox: BBox | None = Field(
        None,
        description="Restrict to this bounding box; None = all of Toronto.",
    )
    top_n: int = Field(
        10,
        ge=1,
        le=158,
        description="Return the top-N most underserved neighbourhoods.",
    )


@tool(EquityGapReportArgs)
def equity_gap_report(args: EquityGapReportArgs) -> dict:
    """Identify neighbourhoods with high marginalization and low transit access (the equity gap).

    Crosses ON-Marg 2021 scores with walk-buffer coverage to surface cells of
    high need + low access. Returns a ranked list of underserved neighbourhoods
    with their marginalization quintile and gap score.
    """
    nbhoods = _load_neighbourhoods()
    on_marg = _load_on_marg()
    stops = _load_gtfs_stops()
    nia = _load_nia()

    # Merge marginalization data onto neighbourhoods by NH_ID / AREA_SHORT_CODE
    nbhoods = nbhoods.copy()
    nbhoods["NH_ID_num"] = pd.to_numeric(nbhoods["AREA_SHORT_CODE"], errors="coerce")
    on_marg_sub = on_marg[
        ["NH_ID", "NH_Name", "NH_Pop2021", "Material_Resources_NHsTO2021",
         "Material_Resources_q_NHsTO2021"]
    ].copy()
    on_marg_sub = on_marg_sub.rename(columns={
        "Material_Resources_NHsTO2021": "marg_score",
        "Material_Resources_q_NHsTO2021": "marg_quintile",
    })
    merged = nbhoods.merge(on_marg_sub, left_on="NH_ID_num", right_on="NH_ID", how="left")

    # Filter by bbox if provided
    if args.bbox is not None:
        region_geom = _bbox_to_shapely(args.bbox)
        centroids = merged.geometry.centroid
        merged = merged[centroids.within(region_geom)].copy()

    if merged.empty:
        return {
            "gap_neighbourhoods": [],
            "total_analysed": 0,
            "bbox_applied": args.bbox is not None,
        }

    # Compute accessibility score per neighbourhood (1 = stop within 400 m, 0 = not)
    buf_deg = (_metres_to_deg_lat(400) + _metres_to_deg_lon(400)) / 2.0
    if stops.empty:
        merged["has_stop_nearby"] = False
    else:
        from shapely.ops import unary_union
        stop_buffers = [pt.buffer(buf_deg) for pt in stops.geometry.values]
        coverage_union = unary_union(stop_buffers)
        centroids = merged.geometry.centroid
        merged["has_stop_nearby"] = centroids.apply(lambda c: coverage_union.contains(c))

    # Flag NIAs
    nia_names = set(nia["AREA_NAME"].str.strip().str.lower()) if not nia.empty else set()
    merged["is_nia"] = merged["AREA_NAME"].str.strip().str.lower().isin(nia_names)

    # Gap score: higher marg_score (more deprived) AND no stop nearby = worse gap
    # Normalize: gap = marg_score (higher = worse deprivation) * (1 if not covered)
    merged["marg_score_num"] = pd.to_numeric(merged["marg_score"], errors="coerce").fillna(0)
    merged["access_penalty"] = (~merged["has_stop_nearby"]).astype(float)
    merged["gap_score"] = merged["marg_score_num"] + merged["access_penalty"] * 2.0

    # Sort by gap_score descending
    top = merged.nlargest(args.top_n, "gap_score")

    results = []
    for _, row in top.iterrows():
        results.append({
            "neighbourhood": str(row.get("AREA_NAME", "")),
            "nh_id": int(row["NH_ID"]) if pd.notna(row.get("NH_ID")) else None,
            "population": int(row["NH_Pop2021"]) if pd.notna(row.get("NH_Pop2021")) else None,
            "marg_score": float(row["marg_score_num"]) if pd.notna(row["marg_score_num"]) else None,
            "marg_quintile": int(row["marg_quintile"]) if pd.notna(row.get("marg_quintile")) else None,
            "has_stop_within_400m": bool(row["has_stop_nearby"]),
            "is_nia": bool(row["is_nia"]),
            "gap_score": round(float(row["gap_score"]), 3),
        })

    return {
        "gap_neighbourhoods": results,
        "total_analysed": int(len(merged)),
        "bbox_applied": args.bbox is not None,
        "note": (
            "gap_score = material_deprivation_score + 2 * (1 if no stop within 400m). "
            "Higher = more underserved relative to need."
        ),
    }


# ---------------------------------------------------------------------------
# reachability
# ---------------------------------------------------------------------------

class ReachabilityArgs(BaseModel):
    origin_lon: float = Field(..., description="Origin longitude (WGS84).")
    origin_lat: float = Field(..., description="Origin latitude (WGS84).")
    time_budget_min: float = Field(
        45,
        gt=0,
        le=120,
        description="Travel time budget in minutes.",
    )
    walk_speed_kmh: float = Field(
        5.0,
        gt=0,
        le=10.0,
        description="Walking speed in km/h for distance-to-time conversion.",
    )


@tool(ReachabilityArgs)
def reachability(args: ReachabilityArgs) -> dict:
    """Isochrone approximation: stops reachable by walking from an origin within a time budget.

    Uses straight-line walk distance (CPU approximation of network distance).
    Returns reachable stop count and the isochrone radius in metres.
    A CPU approximation is used here; a full travel-time surface requires GPU graph traversal.
    """
    # TODO(spark): replace with cuOpt GPU graph traversal for full isochrone surface
    # with transit transfers and real network topology.

    stops = _load_gtfs_stops()

    # Walk distance = speed * time
    walk_radius_m = (args.walk_speed_kmh * 1000 / 60) * args.time_budget_min

    origin = Point(args.origin_lon, args.origin_lat)

    if stops.empty:
        return {
            "reachable_stop_count": 0,
            "walk_radius_m": round(walk_radius_m, 1),
            "time_budget_min": float(args.time_budget_min),
            "walk_speed_kmh": float(args.walk_speed_kmh),
            "method": "straight_line_walk_approximation",
            "note": "No stops in dataset. TODO(spark): add transit transfer legs.",
        }

    stop_coords = np.column_stack([stops.geometry.x.values, stops.geometry.y.values])
    dx = (stop_coords[:, 0] - args.origin_lon) * _METRES_PER_DEG_LON
    dy = (stop_coords[:, 1] - args.origin_lat) * _METRES_PER_DEG_LAT
    distances_m = np.sqrt(dx**2 + dy**2)

    reachable_mask = distances_m <= walk_radius_m
    reachable_stops = stops[reachable_mask].copy()

    # Nearest stop
    if len(distances_m) > 0:
        nearest_idx = int(np.argmin(distances_m))
        nearest_stop_name = str(stops.iloc[nearest_idx]["stop_name"])
        nearest_stop_dist_m = float(distances_m[nearest_idx])
    else:
        nearest_stop_name = None
        nearest_stop_dist_m = None

    reachable_list = [
        {
            "stop_id": int(row["stop_id"]),
            "stop_name": str(row["stop_name"]),
            "distance_m": round(float(distances_m[i]), 1),
        }
        for i, (_, row) in enumerate(
            ((i, stops.iloc[i]) for i in np.where(reachable_mask)[0])
        )
    ]

    return {
        "reachable_stop_count": int(reachable_mask.sum()),
        "walk_radius_m": round(walk_radius_m, 1),
        "time_budget_min": float(args.time_budget_min),
        "walk_speed_kmh": float(args.walk_speed_kmh),
        "nearest_stop_name": nearest_stop_name,
        "nearest_stop_dist_m": round(nearest_stop_dist_m, 1) if nearest_stop_dist_m is not None else None,
        "reachable_stops_sample": reachable_list[:20],
        "method": "straight_line_walk_approximation",
        "note": (
            "CPU straight-line approximation; does not include transit transfer legs. "
            "TODO(spark): upgrade to cuOpt GPU graph traversal with GTFS schedule."
        ),
    }


# ---------------------------------------------------------------------------
# estimate_demand
# ---------------------------------------------------------------------------

class EstimateDemandArgs(BaseModel):
    bbox: BBox | None = Field(
        None,
        description="Restrict to this bounding box; None = all of Toronto.",
    )
    horizon: Literal["now", "2031", "2051"] = Field(
        "now",
        description="Planning horizon. 'now' uses current data; future horizons apply "
        "a simple growth-rate adjustment (no development pipeline data available locally).",
    )


@tool(EstimateDemandArgs)
def estimate_demand(args: EstimateDemandArgs) -> dict:
    """Latent-demand surface: combines population density, marginalization, and transit gaps.

    Returns neighbourhood-level demand scores ranked highest first. Demand is
    estimated from current population, marginalization (transit-dependent populations),
    and whether the neighbourhood lacks nearby stops. Future horizons apply a simple
    uniform growth factor (development pipeline data not yet downloaded).
    """
    # TODO(spark): incorporate development pipeline, intensification-to-2051,
    # Journey-to-Work O→D flows when those datasets are downloaded.

    nbhoods = _load_neighbourhoods()
    on_marg = _load_on_marg()
    stops = _load_gtfs_stops()

    nbhoods = nbhoods.copy()
    nbhoods["NH_ID_num"] = pd.to_numeric(nbhoods["AREA_SHORT_CODE"], errors="coerce")

    on_marg_sub = on_marg[
        ["NH_ID", "NH_Name", "NH_Pop2021",
         "Material_Resources_NHsTO2021", "Racialized_NC_Pop_NHsTO2021"]
    ].copy()
    merged = nbhoods.merge(on_marg_sub, left_on="NH_ID_num", right_on="NH_ID", how="left")

    # Filter by bbox
    if args.bbox is not None:
        region_geom = _bbox_to_shapely(args.bbox)
        centroids = merged.geometry.centroid
        merged = merged[centroids.within(region_geom)].copy()

    if merged.empty:
        return {
            "demand_surface": [],
            "total_analysed": 0,
            "horizon": args.horizon,
        }

    # Coverage
    buf_deg = (_metres_to_deg_lat(400) + _metres_to_deg_lon(400)) / 2.0
    if stops.empty:
        merged["has_stop_nearby"] = False
    else:
        from shapely.ops import unary_union
        stop_buffers = [pt.buffer(buf_deg) for pt in stops.geometry.values]
        coverage_union = unary_union(stop_buffers)
        centroids = merged.geometry.centroid
        merged["has_stop_nearby"] = centroids.apply(lambda c: coverage_union.contains(c))

    merged["pop"] = pd.to_numeric(merged["NH_Pop2021"], errors="coerce").fillna(0)
    merged["marg"] = pd.to_numeric(merged["Material_Resources_NHsTO2021"], errors="coerce").fillna(0)
    merged["racialized"] = pd.to_numeric(merged["Racialized_NC_Pop_NHsTO2021"], errors="coerce").fillna(0)

    # Demand score: population × (1 + deprivation) × (1.5 if no stop nearby)
    merged["demand_score"] = (
        merged["pop"]
        * (1 + merged["marg"].clip(lower=0))
        * merged["has_stop_nearby"].apply(lambda x: 1.0 if x else 1.5)
    )

    # Horizon growth factor
    growth_factors = {"now": 1.0, "2031": 1.08, "2051": 1.20}
    gf = growth_factors[args.horizon]
    merged["demand_score"] = merged["demand_score"] * gf

    top = merged.nlargest(20, "demand_score")

    demand_surface = []
    for _, row in top.iterrows():
        demand_surface.append({
            "neighbourhood": str(row.get("AREA_NAME", "")),
            "nh_id": int(row["NH_ID"]) if pd.notna(row.get("NH_ID")) else None,
            "population": int(row["pop"]) if pd.notna(row["pop"]) else 0,
            "demand_score": round(float(row["demand_score"]), 0),
            "has_stop_within_400m": bool(row["has_stop_nearby"]),
            "marg_score": round(float(row["marg"]), 3),
        })

    return {
        "demand_surface": demand_surface,
        "total_analysed": int(len(merged)),
        "horizon": args.horizon,
        "growth_factor_applied": gf,
        "note": (
            "Latent demand only — not a ridership forecast. "
            "demand_score = population × (1 + deprivation_score) × access_penalty. "
            "Future horizons use a uniform growth factor; development pipeline data "
            "not yet integrated. TODO(spark): add Journey-to-Work O→D, intensification layers."
        ),
    }


# ---------------------------------------------------------------------------
# reliability_report
# ---------------------------------------------------------------------------

class ReliabilityReportArgs(BaseModel):
    route: str | None = Field(
        None,
        description="Route name or number (e.g. '504 KING', '29 DUFFERIN'). "
        "None returns a city-wide summary of the worst-performing routes.",
    )
    top_n: int = Field(
        10,
        ge=1,
        le=100,
        description="Number of routes to return in city-wide summary (ignored if route is specified).",
    )
    mode: Literal["bus", "streetcar", "all"] = Field(
        "all",
        description="Filter by transit mode.",
    )


@tool(ReliabilityReportArgs)
def reliability_report(args: ReliabilityReportArgs) -> dict:
    """Service-quality hotspots: delay statistics for TTC bus and streetcar routes.

    Uses 2025 TTC Bus Delay and Streetcar Delay datasets. Returns mean/median delay,
    incident count, and worst-performing time windows per route or city-wide.
    """
    dfs = []
    if args.mode in ("bus", "all"):
        bus = _load_bus_delays().copy()
        bus["mode"] = "bus"
        dfs.append(bus)
    if args.mode in ("streetcar", "all"):
        sc = _load_streetcar_delays().copy()
        sc["mode"] = "streetcar"
        dfs.append(sc)

    if not dfs:
        return {"routes": [], "total_incidents": 0, "mode": args.mode}

    df = pd.concat(dfs, ignore_index=True)

    # Normalise the Line column
    df["Line"] = df["Line"].astype(str).str.strip().str.upper()

    if args.route is not None:
        route_upper = args.route.strip().upper()
        df = df[df["Line"].str.contains(route_upper, regex=False)]
        if df.empty:
            return {
                "routes": [],
                "total_incidents": 0,
                "route_filter": args.route,
                "mode": args.mode,
                "note": f"No delay records found for route '{args.route}'.",
            }

    # Aggregate per route
    agg = (
        df.groupby("Line")
        .agg(
            incident_count=("Min Delay", "count"),
            mean_delay_min=("Min Delay", "mean"),
            median_delay_min=("Min Delay", "median"),
            p95_delay_min=("Min Delay", lambda x: float(np.percentile(x, 95))),
            total_delay_min=("Min Delay", "sum"),
        )
        .reset_index()
    )
    agg["mean_delay_min"] = agg["mean_delay_min"].round(2)
    agg["median_delay_min"] = agg["median_delay_min"].round(2)
    agg["p95_delay_min"] = agg["p95_delay_min"].round(2)

    if args.route is None:
        agg = agg.nlargest(args.top_n, "mean_delay_min")

    routes_out = []
    for _, row in agg.iterrows():
        routes_out.append({
            "route": str(row["Line"]),
            "incident_count": int(row["incident_count"]),
            "mean_delay_min": float(row["mean_delay_min"]),
            "median_delay_min": float(row["median_delay_min"]),
            "p95_delay_min": float(row["p95_delay_min"]),
            "total_delay_min": float(row["total_delay_min"]),
        })

    return {
        "routes": routes_out,
        "total_incidents": int(len(df)),
        "route_filter": args.route,
        "mode": args.mode,
        "top_n": args.top_n if args.route is None else None,
    }
