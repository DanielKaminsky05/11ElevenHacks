"""TransitRL tools — Family A: City State & Lookup.

Tools that read the current state of the city: get_city_grid, profile_area,
list_transit, compare_areas. Register each with `@tool` from app.tools.registry.

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

import functools
import warnings
from pathlib import Path
from typing import Any, Literal, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import box

from app.data import data_dir
from app.schemas.common import BBox
from app.tools._demand import (
    attraction_nodes as _attraction_nodes,
    opportunity_access_normalised as _opportunity_access_normalised,
)
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# Toronto bounding box (WGS84) — used as the default extent.
# ---------------------------------------------------------------------------
_TORONTO_BBOX = BBox(west=-79.6393, south=43.5810, east=-79.1151, north=43.8555)


# ---------------------------------------------------------------------------
# Private cached loaders — load once, reuse across calls.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_ttc_stops() -> pd.DataFrame:
    """Return TTC GTFS stops as a DataFrame."""
    p = data_dir() / "transit" / "ttc-routes-schedules-gtfs" / "stops.txt"
    return pd.read_csv(p)


@functools.lru_cache(maxsize=1)
def _load_ttc_routes() -> pd.DataFrame:
    p = data_dir() / "transit" / "ttc-routes-schedules-gtfs" / "routes.txt"
    return pd.read_csv(p)


@functools.lru_cache(maxsize=1)
def _load_ttc_trips() -> pd.DataFrame:
    p = data_dir() / "transit" / "ttc-routes-schedules-gtfs" / "trips.txt"
    return pd.read_csv(p)


@functools.lru_cache(maxsize=1)
def _load_go_stops() -> pd.DataFrame:
    p = data_dir() / "transit" / "go-transit-gtfs" / "stops.txt"
    return pd.read_csv(p, encoding="utf-8-sig")


@functools.lru_cache(maxsize=1)
def _load_go_routes() -> pd.DataFrame:
    p = data_dir() / "transit" / "go-transit-gtfs" / "routes.txt"
    return pd.read_csv(p, encoding="utf-8-sig")


@functools.lru_cache(maxsize=1)
def _load_neighbourhoods() -> gpd.GeoDataFrame:
    p = data_dir() / "geospatial" / "neighbourhoods-158.geojson"
    return gpd.read_file(str(p))


@functools.lru_cache(maxsize=1)
def _load_neighbourhood_profiles() -> pd.DataFrame:
    """Return neighbourhood census profile; rows=metrics, cols=neighbourhoods."""
    p = data_dir() / "census-demographics" / "neighbourhood-profiles-2021.xlsx"
    return pd.read_excel(str(p))


@functools.lru_cache(maxsize=1)
def _load_ward_profiles() -> pd.DataFrame:
    """Return ward census profile (2021 One Variable sheet).
    Row 17 is the header row (0-indexed), with Toronto + Ward 1..25 columns.
    """
    p = data_dir() / "census-demographics" / "ward-profiles-census-2011-2021.xlsx"
    df = pd.read_excel(
        str(p),
        sheet_name="2021 One Variable",
        header=None,
        skiprows=17,
    )
    # Row 0 after skip is the column header ("", Toronto, Ward 1, ...)
    df.columns = df.iloc[0].fillna("Metric")
    df = df.iloc[1:].reset_index(drop=True)
    return df


@functools.lru_cache(maxsize=1)
def _load_transit_stations() -> gpd.GeoDataFrame:
    p = data_dir() / "geospatial" / "transit-stations.geojson"
    return gpd.read_file(str(p))


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------


def _bbox_to_shapely(bbox: BBox):
    return box(bbox.west, bbox.south, bbox.east, bbox.north)


@functools.lru_cache(maxsize=1)
def _neighbourhood_centroids_wgs84() -> gpd.GeoDataFrame:
    """Return a GeoDataFrame of neighbourhood centroids in WGS84.

    Reprojects to UTM Zone 17N (EPSG:32617) for accurate centroid computation,
    then converts the result back to WGS84 lon/lat columns.
    """
    gdf = _load_neighbourhoods()
    projected = gdf.to_crs("EPSG:32617")
    c = projected.geometry.centroid.to_crs("EPSG:4326")
    out = gdf[["AREA_ID", "AREA_NAME", "geometry"]].copy()
    out["centroid_lon"] = c.x
    out["centroid_lat"] = c.y
    return out


def _filter_stops_by_bbox(
    stops: pd.DataFrame, bbox: BBox, lat_col: str = "stop_lat", lon_col: str = "stop_lon"
) -> pd.DataFrame:
    return stops[
        (stops[lat_col] >= bbox.south)
        & (stops[lat_col] <= bbox.north)
        & (stops[lon_col] >= bbox.west)
        & (stops[lon_col] <= bbox.east)
    ]


# ---------------------------------------------------------------------------
# Helper: look up a neighbourhood name from a string (case-insensitive partial)
# ---------------------------------------------------------------------------


def _find_neighbourhood(name: str) -> Optional[pd.Series]:
    """Return the neighbourhoods-158 row whose AREA_NAME best matches *name*."""
    gdf = _load_neighbourhoods()
    lower = name.strip().lower()
    mask = gdf["AREA_NAME"].str.lower().str.contains(lower, regex=False)
    matches = gdf[mask]
    if matches.empty:
        return None
    return matches.iloc[0]


def _area_km2(geom) -> Optional[float]:
    """Land area of a neighbourhood polygon, in km².

    Reproject the single polygon to UTM Zone 17N (metres) so `.area` is a true
    planar area, then convert m² → km². Returns None if the geometry is missing.
    """
    if geom is None:
        return None
    projected = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs("EPSG:32617")
    return float(projected.area.iloc[0]) / 1_000_000.0


def _get_profile_metric(
    profile_df: pd.DataFrame, metric_substr: str, neighbourhood_name: str
) -> Optional[Any]:
    """Return scalar profile value for a given metric substring and neighbourhood column."""
    mask = profile_df["Neighbourhood Name"].str.strip().str.lower().str.contains(
        metric_substr.lower(), regex=False, na=False
    )
    rows = profile_df[mask]
    if rows.empty or neighbourhood_name not in profile_df.columns:
        return None
    val = rows.iloc[0][neighbourhood_name]
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Area-distributed rasterization: spread a per-neighbourhood value across the
# grid cells that fall inside each neighbourhood polygon. This turns the coarse
# 158-point census into a proper field, so large neighbourhoods occupy many cells
# and gaps appear wherever a cell sits far from existing service.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=8)
def _cell_neighbourhood_assignment(
    west: float, south: float, east: float, north: float, N: int
) -> pd.Series:
    """For an N×N grid over the bbox, return the containing neighbourhood AREA_NAME
    per cell (NaN if outside the city), indexed in grid[lat_row, lon_col] order.
    """
    lons = np.linspace(west, east, N + 1)
    lats = np.linspace(south, north, N + 1)
    lon_c = 0.5 * (lons[:-1] + lons[1:])
    lat_c = 0.5 * (lats[:-1] + lats[1:])
    lon_mesh, lat_mesh = np.meshgrid(lon_c, lat_c)  # grid[lat, lon] order
    pts = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(lon_mesh.ravel(), lat_mesh.ravel()),
        crs="EPSG:4326",
    )
    nbhd = _load_neighbourhoods()[["AREA_NAME", "geometry"]]
    joined = gpd.sjoin(pts, nbhd, how="left", predicate="within")
    # A cell on a shared border can match >1 polygon; keep the first match.
    joined = joined[~joined.index.duplicated(keep="first")].sort_index()
    return joined["AREA_NAME"].reset_index(drop=True)


def _nbhd_value_map(metric_exact: str, scale: float = 1.0) -> dict[str, float]:
    """Map neighbourhood name → profile metric value (× scale)."""
    prof = _load_neighbourhood_profiles()
    row = prof[prof["Neighbourhood Name"].str.strip() == metric_exact]
    out: dict[str, float] = {}
    if row.empty:
        return out
    r = row.iloc[0]
    for col in prof.columns:
        if col == "Neighbourhood Name":
            continue
        try:
            out[col] = float(r[col]) * scale
        except (TypeError, ValueError):
            continue
    return out


def _area_distributed_grid(
    bbox: BBox, N: int, metric_exact: str, *, density: bool, scale: float = 1.0
) -> np.ndarray:
    """Rasterize a per-neighbourhood metric over the grid.

    density=True spreads a total (e.g. population) evenly across the cells of each
    neighbourhood (so the grid sums to ≈ the city total); density=False assigns the
    value as-is to every cell of the neighbourhood (e.g. a low-income *fraction*).
    """
    names = _cell_neighbourhood_assignment(
        bbox.west, bbox.south, bbox.east, bbox.north, N
    )
    value_map = _nbhd_value_map(metric_exact, scale=scale)
    counts = names.value_counts()  # cells per neighbourhood (NaN excluded)

    def _cell(nm: object) -> float:
        if not isinstance(nm, str) or nm not in value_map:
            return 0.0
        v = value_map[nm]
        return v / counts[nm] if density else v

    flat = names.map(_cell).to_numpy(dtype=float)
    return flat.reshape(N, N)


# ===========================================================================
# Tool: get_city_grid
# ===========================================================================


class GetCityGridArgs(BaseModel):
    """Input for get_city_grid."""

    bbox: Optional[BBox] = Field(
        None,
        description="Area to rasterize. None = whole Toronto extent.",
    )
    channels: list[
        Literal[
            "population",
            "stops",
            "income",
            "need",
            "destinations",
            "opportunity_access",
            "network",
            "boundary",
        ]
    ] = Field(
        default=["population", "stops"],
        description="Grid channels to include in the output tensor.",
        min_length=1,
    )
    resolution: int = Field(
        30,
        ge=5,
        le=200,
        description="Number of cells per axis (NxN grid). Must be between 5 and 200.",
    )

    @model_validator(mode="after")
    def _check_bbox(self) -> "GetCityGridArgs":
        b = self.bbox
        if b is not None:
            if b.east <= b.west:
                raise ValueError("bbox.east must be greater than bbox.west")
            if b.north <= b.south:
                raise ValueError("bbox.north must be greater than bbox.south")
        return self


@tool(GetCityGridArgs)
def get_city_grid(args: GetCityGridArgs) -> dict:
    """Rasterize open-data layers (population, stops, income, ...) into a multi-channel NxN grid
    tensor for the map/optimizer. Use for the gridded/spatial view or to feed the optimizer. For
    one neighbourhood's stats by name use profile_area; to compare named neighbourhoods use
    compare_areas."""
    bbox = args.bbox or _TORONTO_BBOX
    N = args.resolution

    # Build lon/lat bin edges
    lons = np.linspace(bbox.west, bbox.east, N + 1)
    lats = np.linspace(bbox.south, bbox.north, N + 1)
    lon_centres = 0.5 * (lons[:-1] + lons[1:])
    lat_centres = 0.5 * (lats[:-1] + lats[1:])

    channels_out: dict[str, list] = {}

    for channel in args.channels:
        grid = np.zeros((N, N), dtype=float)

        if channel == "stops":
            # Bin TTC stops into grid cells
            ttc = _filter_stops_by_bbox(_load_ttc_stops(), bbox)
            go = _filter_stops_by_bbox(_load_go_stops(), bbox)
            all_stops = pd.concat(
                [
                    ttc[["stop_lat", "stop_lon"]],
                    go[["stop_lat", "stop_lon"]],
                ],
                ignore_index=True,
            )
            if not all_stops.empty:
                lon_idx = np.clip(
                    np.searchsorted(lons[1:], all_stops["stop_lon"].values), 0, N - 1
                )
                lat_idx = np.clip(
                    np.searchsorted(lats[1:], all_stops["stop_lat"].values), 0, N - 1
                )
                for lo, la in zip(lon_idx, lat_idx):
                    grid[la, lo] += 1
            # TODO(spark): replace with cuSpatial point-in-polygon rasterization
            # across the full city grid for sub-second performance on the DGX Spark.

        elif channel == "population":
            # Spread each neighbourhood's population evenly across the grid cells
            # inside its polygon → a population *field*, not 158 centroid spikes.
            grid = _area_distributed_grid(
                bbox,
                N,
                "Total - Age groups of the population - 25% sample data",
                density=True,
            )
            # TODO(spark): use cuSpatial spatial join + cuDF groupby for whole-city
            # rasterization in GPU memory; swap to census-DA population for detail.

        elif channel == "income":
            # Bin neighbourhood centroids weighted by median household income
            centroids = _neighbourhood_centroids_wgs84()
            prof = _load_neighbourhood_profiles()
            in_bbox = centroids[
                (centroids["centroid_lon"] >= bbox.west)
                & (centroids["centroid_lon"] <= bbox.east)
                & (centroids["centroid_lat"] >= bbox.south)
                & (centroids["centroid_lat"] <= bbox.north)
            ]
            income_row = prof[
                prof["Neighbourhood Name"].str.strip()
                == "  Median after-tax income of household in 2020 ($)"
            ]
            for _, row in in_bbox.iterrows():
                nb_name = row["AREA_NAME"]
                income = None
                if not income_row.empty and nb_name in prof.columns:
                    try:
                        income = float(income_row.iloc[0][nb_name])
                    except (TypeError, ValueError):
                        income = 0.0
                if income is None:
                    income = 0.0
                lo_idx = int(
                    np.clip(
                        np.searchsorted(lons[1:], row["centroid_lon"]), 0, N - 1
                    )
                )
                la_idx = int(
                    np.clip(
                        np.searchsorted(lats[1:], row["centroid_lat"]), 0, N - 1
                    )
                )
                grid[la_idx, lo_idx] = income
            # TODO(spark): load income raster from GPU-resident census tile store.

        elif channel == "need":
            # Low-income prevalence as a fraction in [0, 1], assigned to every cell
            # in each neighbourhood — the equity "need" signal the optimizer's
            # reward weights underserved residents by.
            grid = _area_distributed_grid(
                bbox,
                N,
                "Prevalence of low income based on the Low-income measure, after tax (LIM-AT) (%)",
                density=False,
                scale=1.0 / 100.0,
            )
            grid = np.clip(grid, 0.0, 1.0)
            # TODO(spark): blend ON-Marg material-deprivation + NIA flags into the
            # need signal (loaders exist in diagnostics.py); GPU raster via cuSpatial.

        elif channel == "destinations":
            # Job mass binned to cells: where the opportunities people travel TO
            # actually are. Each Urban Growth Centre drops its relative employment
            # weight into the cell it falls in (a point-mass layer, like `stops`).
            for node in _attraction_nodes():
                nlon, nlat = float(node["lon"]), float(node["lat"])
                if not (bbox.west <= nlon <= bbox.east and bbox.south <= nlat <= bbox.north):
                    continue
                lo_idx = int(np.clip(np.searchsorted(lons[1:], nlon), 0, N - 1))
                la_idx = int(np.clip(np.searchsorted(lats[1:], nlat), 0, N - 1))
                grid[la_idx, lo_idx] += float(node["weight"])
            # TODO(spark): swap the 5 growth-centre anchors for a geocoded jobs raster
            # (Census place-of-work) via cuSpatial rasterization.

        elif channel == "opportunity_access":
            # Hansen gravity access to jobs/opportunities, in [0, 1] — the demand
            # side of the network. Validated against StatCan SAM's transit
            # employment-access index (Spearman ≈ 0.82); see app/tools/_demand.py.
            lon_mesh, lat_mesh = np.meshgrid(lon_centres, lat_centres)  # [lat, lon]
            grid = _opportunity_access_normalised(
                lon_mesh.ravel(), lat_mesh.ravel()
            ).reshape(N, N)
            # TODO(spark): replace straight-line node gravity with a real GTFS
            # transit travel-time surface (cuOpt graph traversal).

        elif channel in ("network", "boundary"):
            # Stub channels — placeholder zeros.
            # TODO(spark): populate from Centreline + Pedestrian Network (network)
            # and Neighbourhoods-158 / Wards (boundary) via cuSpatial rasterization.
            pass  # grid already zeros

        channels_out[channel] = grid.tolist()

    return {
        "bbox": {
            "west": bbox.west,
            "south": bbox.south,
            "east": bbox.east,
            "north": bbox.north,
        },
        "resolution": N,
        "channels": list(channels_out.keys()),
        "grid": channels_out,
        "lon_centres": lon_centres.tolist(),
        "lat_centres": lat_centres.tolist(),
    }


# ===========================================================================
# Tool: profile_area
# ===========================================================================


_PROFILE_METRICS_DEFAULT = [
    "population",
    "median_age",
    "median_household_income",
    "pct_low_income",
    "stop_count",
    "area_km2",
    "population_density",
]

_ALLOWED_METRICS = Literal[
    "population",
    "median_age",
    "median_household_income",
    "pct_low_income",
    "stop_count",
    "area_km2",
    "population_density",
]


class ProfileAreaArgs(BaseModel):
    """Input for profile_area."""

    name: str = Field(
        ...,
        min_length=1,
        description="Neighbourhood or area name (partial, case-insensitive match against Toronto's 158 neighbourhoods).",
    )
    metrics: list[_ALLOWED_METRICS] = Field(
        default_factory=lambda: list(_PROFILE_METRICS_DEFAULT),
        description="Which metrics to include in the profile. population_density is "
        "residents per km² (population / land area); area_km2 is the land area.",
        min_length=1,
    )


@tool(ProfileAreaArgs)
def profile_area(args: ProfileAreaArgs) -> dict:
    """Return a census + transit dossier (population, income, low-income %, stop count, land
    area, population density) for ONE Toronto neighbourhood by name. Use for "what is the
    population/size/density of X" / "tell me about X". population_density is residents per km².
    For multiple areas use compare_areas; for the gridded map view use get_city_grid."""
    row = _find_neighbourhood(args.name)
    if row is None:
        return {
            "error": f"No neighbourhood found matching {args.name!r}. "
            "Use a partial name from Toronto's 158 neighbourhoods.",
            "matched_name": None,
            "metrics": {},
        }

    nb_name = row["AREA_NAME"]
    prof = _load_neighbourhood_profiles()
    result: dict[str, Any] = {}

    for metric in args.metrics:
        if metric == "population":
            val = _get_profile_metric(
                prof,
                "Total - Age groups of the population - 25% sample data",
                nb_name,
            )
            result["population"] = int(val) if val is not None else None

        elif metric == "median_age":
            val = _get_profile_metric(prof, "Median age of the population", nb_name)
            result["median_age"] = float(val) if val is not None else None

        elif metric == "median_household_income":
            val = _get_profile_metric(
                prof, "Median after-tax income of household in 2020 ($)", nb_name
            )
            result["median_household_income"] = float(val) if val is not None else None

        elif metric == "pct_low_income":
            val = _get_profile_metric(
                prof,
                "Prevalence of low income based on the Low-income measure, after tax (LIM-AT) (%)",
                nb_name,
            )
            result["pct_low_income"] = float(val) if val is not None else None

        elif metric == "stop_count":
            # Count TTC stops within the neighbourhood polygon
            geom = row["geometry"]
            ttc = _load_ttc_stops()
            stops_gdf = gpd.GeoDataFrame(
                ttc,
                geometry=gpd.points_from_xy(ttc["stop_lon"], ttc["stop_lat"]),
                crs="EPSG:4326",
            )
            within = stops_gdf[stops_gdf.geometry.within(geom)]
            result["stop_count"] = int(len(within))

        elif metric == "area_km2":
            area = _area_km2(row["geometry"])
            result["area_km2"] = round(area, 2) if area is not None else None

        elif metric == "population_density":
            # Residents per km² — derived, so the agent can answer "how dense is X"
            # instead of fumbling population for density (the bug in the transcript).
            pop = _get_profile_metric(
                prof,
                "Total - Age groups of the population - 25% sample data",
                nb_name,
            )
            area = _area_km2(row["geometry"])
            result["population_density"] = (
                round(pop / area, 1) if pop and area else None
            )

    return {
        "matched_name": nb_name,
        "area_id": int(row["AREA_ID"]),
        "metrics": result,
    }


# ===========================================================================
# Tool: list_transit
# ===========================================================================


class ListTransitArgs(BaseModel):
    """Input for list_transit."""

    bbox: Optional[BBox] = Field(
        None,
        description="Restrict results to stops and routes whose stops fall in this box. None = whole city.",
    )
    modes: list[Literal["bus", "subway", "streetcar", "rail"]] = Field(
        default=["bus", "subway", "streetcar", "rail"],
        description="Transit modes to include.",
        min_length=1,
    )
    limit: int = Field(
        500,
        ge=1,
        le=5000,
        description="Maximum number of stops to return.",
    )

    @model_validator(mode="after")
    def _check_bbox(self) -> "ListTransitArgs":
        b = self.bbox
        if b is not None:
            if b.east <= b.west:
                raise ValueError("bbox.east must be greater than bbox.west")
            if b.north <= b.south:
                raise ValueError("bbox.north must be greater than bbox.south")
        return self


# GTFS route_type → human mode
_GTFS_MODE_MAP = {
    0: "streetcar",  # Tram/light rail
    1: "subway",     # Subway/Metro
    2: "rail",       # Rail (GO)
    3: "bus",        # Bus
}


@tool(ListTransitArgs)
def list_transit(args: ListTransitArgs) -> dict:
    """List transit stops and routes in an area, filtered by mode."""
    bbox = args.bbox or _TORONTO_BBOX
    mode_set = set(args.modes)

    # --- TTC stops ---
    ttc_stops = _filter_stops_by_bbox(_load_ttc_stops(), bbox)
    ttc_routes = _load_ttc_routes()
    ttc_trips = _load_ttc_trips()

    # Map each TTC stop to route_type via stop_times → trips → routes (heavy).
    # Instead, use the route types available in routes.txt directly.
    # Build a lookup: route_id → mode
    ttc_route_mode = {
        int(r.route_id): _GTFS_MODE_MAP.get(int(r.route_type), "bus")
        for _, r in ttc_routes.iterrows()
    }

    # Filter TTC routes by requested modes
    allowed_ttc_route_ids = {
        rid for rid, mode in ttc_route_mode.items() if mode in mode_set
    }

    # --- GO stops ---
    go_stops_raw = _filter_stops_by_bbox(_load_go_stops(), bbox)
    go_routes = _load_go_routes()
    include_go = "rail" in mode_set

    # Build output stops list (TTC)
    stop_records: list[dict] = []
    for _, s in ttc_stops.head(args.limit).iterrows():
        stop_records.append(
            {
                "stop_id": str(s["stop_id"]),
                "name": str(s["stop_name"]),
                "lat": float(s["stop_lat"]),
                "lon": float(s["stop_lon"]),
                "agency": "TTC",
                "mode": None,  # enriched below if needed
            }
        )

    # Add GO stops
    if include_go:
        for _, s in go_stops_raw.iterrows():
            if len(stop_records) >= args.limit:
                break
            stop_records.append(
                {
                    "stop_id": str(s["stop_id"]),
                    "name": str(s["stop_name"]),
                    "lat": float(s["stop_lat"]),
                    "lon": float(s["stop_lon"]),
                    "agency": "GO",
                    "mode": "rail",
                }
            )

    # Summarise routes
    def _routes_summary(routes_df: pd.DataFrame, agency: str) -> list[dict]:
        out = []
        for _, r in routes_df.iterrows():
            mode = _GTFS_MODE_MAP.get(int(r.get("route_type", 3)), "bus")
            if mode not in mode_set:
                continue
            out.append(
                {
                    "route_id": str(r["route_id"]),
                    "short_name": str(r.get("route_short_name", "")),
                    "long_name": str(r.get("route_long_name", "")),
                    "mode": mode,
                    "agency": agency,
                }
            )
        return out

    routes_out = _routes_summary(ttc_routes, "TTC")
    if include_go:
        routes_out += _routes_summary(go_routes, "GO")

    return {
        "bbox": {
            "west": bbox.west,
            "south": bbox.south,
            "east": bbox.east,
            "north": bbox.north,
        },
        "modes": list(mode_set),
        "stop_count": len(stop_records),
        "stops": stop_records,
        "route_count": len(routes_out),
        "routes": routes_out,
    }


# ===========================================================================
# Tool: compare_areas
# ===========================================================================


class CompareAreasArgs(BaseModel):
    """Input for compare_areas."""

    areas: list[str] = Field(
        ...,
        min_length=2,
        description="List of at least two neighbourhood names to compare (partial, case-insensitive).",
    )
    metrics: list[_ALLOWED_METRICS] = Field(
        default_factory=lambda: list(_PROFILE_METRICS_DEFAULT),
        description="Metrics to compare across areas. Includes area_km2 and "
        "population_density (residents per km²).",
        min_length=1,
    )
    sort_by: Optional[str] = Field(
        None,
        description="Metric name to sort the ranking by (descending). Must be one of the requested metrics.",
    )

    @model_validator(mode="after")
    def _check_sort_by(self) -> "CompareAreasArgs":
        if self.sort_by is not None and self.sort_by not in self.metrics:
            raise ValueError(
                f"sort_by={self.sort_by!r} must be one of the requested metrics: {self.metrics}"
            )
        return self


@tool(CompareAreasArgs)
def compare_areas(args: CompareAreasArgs) -> dict:
    """Side-by-side comparison of census + transit metrics across MULTIPLE named Toronto
    neighbourhoods. Use when the planner names two or more areas ("compare X and Y"). For a
    single area use profile_area."""
    profile_args_metrics = args.metrics  # same metric list reused for each area
    rows: list[dict] = []
    not_found: list[str] = []

    for area_name in args.areas:
        result = profile_area(
            ProfileAreaArgs(name=area_name, metrics=profile_args_metrics)
        )
        if result.get("matched_name") is None:
            not_found.append(area_name)
            continue
        row: dict[str, Any] = {"area": result["matched_name"]}
        row.update(result["metrics"])
        rows.append(row)

    # Sort if requested
    if args.sort_by and rows:
        rows.sort(key=lambda r: (r.get(args.sort_by) or 0), reverse=True)

    return {
        "areas": rows,
        "metrics": list(args.metrics),
        "not_found": not_found,
        "ranked_by": args.sort_by,
    }
