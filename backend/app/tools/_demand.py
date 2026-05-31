"""O-D demand substrate: gravity access-to-opportunities, grounded in real data.

This module is the shared **origin-destination demand** layer that several tools
consume (get_city_grid's `destinations`/`opportunity_access` channels, the
optimizer reward, estimate_demand, reachability). It is *not* a `@tool` family —
it has no registered tools — so it lives under a leading underscore.

The model is **Hansen accessibility to opportunities** (an implicit gravity O-D),
not a literal observed trip matrix:

    A_i = Σ_j  w_j · exp( -dist(i, j) / d0 )      # opportunities reachable from i

where the destinations `j` are Toronto's official Urban Growth Centres (the
dominant employment concentrations) weighted by relative job mass. This is a
*latent* access model, **not a ridership forecast** — the same honesty boundary
the rest of the toolbox carries.

**Grounding / validation.** Statistics Canada's Spatial Access Measures (SAM)
publish a real, per-dissemination-block transit access-to-employment index
(`acs_idx_emp`, peak). Our gravity surface correlates with it at Spearman ≈ 0.82
across Toronto's dissemination areas (see tests/tools/test_demand.py). SAM thus
serves as both a validation anchor and the per-origin baseline the reward credits
*new* access on top of.

# TODO(spark): replace the straight-line node-gravity cost with a real GTFS
# transit travel-time surface (cuOpt graph traversal) and vectorise A_i over all
# cells × destinations with cuSpatial/cuDF.
"""

from __future__ import annotations

import functools
import math

import geopandas as gpd
import numpy as np
import pandas as pd

from app.data import data_dir


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Metres per degree at Toronto's latitude (matches city_state / optimization).
_M_PER_DEG_LAT = 111_139.0
_M_PER_DEG_LON = 111_139.0 * math.cos(math.radians(43.7))

# Gravity decay scale (metres) for job access. Commute-to-opportunity operates at
# a kilometres scale, not the ~400 m walk scale. Calibrated against SAM's transit
# employment-access index: Spearman is a robust ~0.80–0.82 for d0 in 4–12 km;
# 8 km sits at the plateau. This is the knob to recalibrate if a Journey-to-Work
# decay or a real transit travel-time surface is wired in.
_JOB_ACCESS_D0_M = 8_000.0

# Toronto's five Urban Growth Centres (Provincial Growth Plan) — the dominant
# employment concentrations and the canonical "where commute trips go" anchors.
# Weights are relative job mass (Downtown's Financial District dwarfs the rest).
# Coordinates are WGS84 lon/lat of each centre's core.
#
# Source for the typology: City of Toronto Employment Survey "Urban Economic
# Structure Areas" (Downtown / Centres). Weights are order-of-magnitude relative
# employment, not exact counts — the model is latent, not a forecast.
ATTRACTION_NODES: tuple[dict[str, float | str], ...] = (
    {"name": "Downtown / Financial District", "lon": -79.3806, "lat": 43.6487, "weight": 1.00},
    {"name": "North York Centre", "lon": -79.4112, "lat": 43.7615, "weight": 0.40},
    {"name": "Yonge-Eglinton Centre", "lon": -79.3989, "lat": 43.7064, "weight": 0.30},
    {"name": "Scarborough Centre", "lon": -79.2585, "lat": 43.7736, "weight": 0.28},
    {"name": "Etobicoke Centre", "lon": -79.5350, "lat": 43.6450, "weight": 0.22},
)

# SAM column carrying the normalised transit access-to-employment index, [0, 1].
_SAM_EMP_COL = "acs_idx_emp"


# ---------------------------------------------------------------------------
# Real-data loaders (cached: load once, reuse across calls)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def load_sam_job_access() -> pd.DataFrame:
    """Per-dissemination-area transit access-to-employment from StatCan SAM (peak).

    Returns a DataFrame indexed by string ``DAUID`` with one column
    ``emp_access`` in [0, 1] — the real, network-grounded baseline access to jobs
    by transit. Filtered to the City of Toronto (CSDNAME == 'Toronto').

    SAM is published at dissemination-*block* granularity (11-digit DBUID); we
    aggregate to dissemination *area* (8-digit DAUID = DBUID // 1000) to join the
    DA boundary file we hold locally.
    """
    p = (
        data_dir()
        / "census-demographics"
        / "spatial-access-measures-2024"
        / "acs_public_transit_peak.csv"
    )
    df = pd.read_csv(
        p,
        usecols=["DBUID", "CSDNAME", _SAM_EMP_COL],
        dtype={"DBUID": "int64"},
        low_memory=False,
    )
    df = df[df["CSDNAME"].astype(str) == "Toronto"].copy()
    df["DAUID"] = (df["DBUID"] // 1000).astype(str)
    df["emp_access"] = pd.to_numeric(df[_SAM_EMP_COL], errors="coerce")
    da = (
        df.dropna(subset=["emp_access"])
        .groupby("DAUID", as_index=True)["emp_access"]
        .mean()
        .to_frame()
    )
    return da


@functools.lru_cache(maxsize=1)
def _da_centroids_wgs84() -> pd.DataFrame:
    """Dissemination-area centroids as a DataFrame indexed by string ``DAUID``.

    Reprojects the StatCan DA boundaries (EPSG:3347 Lambert) to UTM 17N for an
    accurate centroid, then back to WGS84 lon/lat.
    """
    p = (
        data_dir()
        / "census-demographics"
        / "statcan-2021-da-boundaries"
        / "lda_000a21a_e.shp"
    )
    gdf = gpd.read_file(str(p), columns=["DAUID", "geometry"])
    projected = gdf.to_crs("EPSG:32617")
    c = projected.geometry.centroid.to_crs("EPSG:4326")
    out = pd.DataFrame(
        {"lon": c.x.to_numpy(), "lat": c.y.to_numpy()},
        index=gdf["DAUID"].astype(str).to_numpy(),
    )
    out.index.name = "DAUID"
    return out


@functools.lru_cache(maxsize=1)
def sam_access_points() -> pd.DataFrame:
    """The real baseline job-access surface as points.

    Joins SAM transit employment-access to DA centroids → a DataFrame with columns
    ``lon``, ``lat``, ``emp_access`` (one row per Toronto DA that has both). This
    is the per-origin baseline ``A0`` the optimizer credits *new* access on top of,
    and the validation target for the gravity model below.
    """
    sam = load_sam_job_access()
    cent = _da_centroids_wgs84()
    out = sam.join(cent, how="inner").dropna(subset=["lon", "lat", "emp_access"])
    return out[["lon", "lat", "emp_access"]].reset_index()


# ---------------------------------------------------------------------------
# Gravity opportunity-access model (pure; counterfactual-capable)
# ---------------------------------------------------------------------------


def attraction_nodes() -> tuple[dict[str, float | str], ...]:
    """The destination/attraction nodes (Urban Growth Centres) with job weights."""
    return ATTRACTION_NODES


def gravity_job_access(
    lon: np.ndarray | float,
    lat: np.ndarray | float,
    d0_m: float = _JOB_ACCESS_D0_M,
) -> np.ndarray:
    """Hansen gravity access to job-bearing destinations for arbitrary points.

    ``A_i = Σ_j w_j · exp(-dist(i, j) / d0)`` over the attraction nodes. Vectorised
    and pure: accepts a scalar or array of lon/lat and returns an array of the same
    shape with the access value at each point. Distances use the local
    equirectangular metre approximation (good at Toronto's extent).

    Not normalised — callers that need [0, 1] should use
    :func:`opportunity_access_normalised`.
    """
    lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
    lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
    access = np.zeros(lon_arr.shape, dtype=float)
    for node in ATTRACTION_NODES:
        dx = (lon_arr - float(node["lon"])) * _M_PER_DEG_LON
        dy = (lat_arr - float(node["lat"])) * _M_PER_DEG_LAT
        dist = np.sqrt(dx * dx + dy * dy)
        access += float(node["weight"]) * np.exp(-dist / d0_m)
    return access


@functools.lru_cache(maxsize=1)
def _opportunity_access_max() -> float:
    """City-wide maximum of the gravity field — a stable [0, 1] normaliser.

    The field peaks at the highest-weight node (Downtown), so the max over the node
    locations is the global maximum and a fixed reference independent of any
    query bbox or resolution (keeps sub-city grids comparable to whole-city ones).
    """
    lons = np.array([float(n["lon"]) for n in ATTRACTION_NODES])
    lats = np.array([float(n["lat"]) for n in ATTRACTION_NODES])
    return float(gravity_job_access(lons, lats).max())


def opportunity_access_normalised(
    lon: np.ndarray | float,
    lat: np.ndarray | float,
    d0_m: float = _JOB_ACCESS_D0_M,
) -> np.ndarray:
    """Gravity job-access scaled to [0, 1] by the fixed city-wide maximum.

    1.0 ≈ Downtown core; fades to ~0 at the transit-poor periphery. The channel the
    map renders and the optimizer reads as the opportunity-access surface.
    """
    return np.clip(
        gravity_job_access(lon, lat, d0_m) / _opportunity_access_max(), 0.0, 1.0
    )
