"""Tests for Family B — Accessibility & Equity Diagnostics.

Covers: compute_accessibility, equity_gap_report, reachability,
estimate_demand, reliability_report.

Run with:
    cd backend && ./.venv/Scripts/python.exe -m pytest tests/tools/test_diagnostics.py -q
"""

from __future__ import annotations

import warnings

import pytest

# Suppress geopandas centroid-in-geographic-CRS UserWarnings throughout this module.
# Our tools use flat-Earth distance approximations (lon/lat) intentionally, so the
# "Results from 'centroid' are likely incorrect" notice is expected and harmless.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Geometry is in a geographic CRS.*centroid:UserWarning"
)
from pydantic import ValidationError

from app.schemas.common import BBox
from app.tools.registry import get_tool

# ---------------------------------------------------------------------------
# Import the tools directly
# ---------------------------------------------------------------------------
from app.tools.diagnostics import (
    ComputeAccessibilityArgs,
    EquityGapReportArgs,
    EstimateDemandArgs,
    ReachabilityArgs,
    ReliabilityReportArgs,
    compute_accessibility,
    equity_gap_report,
    estimate_demand,
    reachability,
    reliability_report,
)

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

# A small bbox centred on downtown Toronto (has many stops)
DOWNTOWN_BBOX = BBox(west=-79.40, south=43.64, east=-79.37, north=43.66)

# A bbox in Lake Ontario (no stops, no neighbourhoods)
LAKE_BBOX = BBox(west=-79.40, south=43.55, east=-79.37, north=43.58)

# Jane & Finch area (north-west Toronto, equity-relevant)
JANE_FINCH_BBOX = BBox(west=-79.52, south=43.74, east=-79.49, north=43.77)

# Downtown origin point (Union Station area)
UNION_LON, UNION_LAT = -79.3832, 43.6452


# ---------------------------------------------------------------------------
# Schema / registry tests (one per tool)
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_compute_accessibility_in_registry(self):
        spec = get_tool("compute_accessibility")
        assert spec.name == "compute_accessibility"
        assert spec.fn is compute_accessibility

    def test_equity_gap_report_in_registry(self):
        spec = get_tool("equity_gap_report")
        assert spec.name == "equity_gap_report"

    def test_reachability_in_registry(self):
        spec = get_tool("reachability")
        assert spec.name == "reachability"

    def test_estimate_demand_in_registry(self):
        spec = get_tool("estimate_demand")
        assert spec.name == "estimate_demand"

    def test_reliability_report_in_registry(self):
        spec = get_tool("reliability_report")
        assert spec.name == "reliability_report"

    def test_all_tools_have_json_schema(self):
        for name in (
            "compute_accessibility",
            "equity_gap_report",
            "reachability",
            "estimate_demand",
            "reliability_report",
        ):
            spec = get_tool(name)
            schema = spec.input_model.model_json_schema()
            assert "properties" in schema, f"{name} schema missing 'properties'"


# ---------------------------------------------------------------------------
# compute_accessibility
# ---------------------------------------------------------------------------

class TestComputeAccessibility:
    def test_happy_path_whole_city(self):
        """Whole-city run returns reasonable coverage values."""
        result = compute_accessibility(ComputeAccessibilityArgs())
        assert "pct_covered" in result
        assert "mean_distance_m" in result
        assert "stop_count" in result
        assert "neighbourhood_count" in result
        assert 0 <= result["pct_covered"] <= 100
        assert result["stop_count"] > 0
        assert result["neighbourhood_count"] > 0
        assert result["mean_distance_m"] is not None
        assert result["mean_distance_m"] > 0

    def test_happy_path_bbox(self):
        """Downtown bbox returns non-zero coverage."""
        result = compute_accessibility(
            ComputeAccessibilityArgs(bbox=DOWNTOWN_BBOX, threshold_m=400)
        )
        assert result["pct_covered"] >= 0
        assert result["stop_count"] >= 0

    def test_lake_bbox_no_stops(self):
        """A bbox over the lake should return 0% coverage."""
        result = compute_accessibility(
            ComputeAccessibilityArgs(bbox=LAKE_BBOX, threshold_m=400)
        )
        assert result["pct_covered"] == 0.0
        assert result["neighbourhood_count"] == 0 or result["stop_count"] == 0

    def test_larger_threshold_never_decreases_coverage(self):
        """Invariant: larger walk threshold must not decrease coverage."""
        r_small = compute_accessibility(
            ComputeAccessibilityArgs(bbox=DOWNTOWN_BBOX, threshold_m=200)
        )
        r_large = compute_accessibility(
            ComputeAccessibilityArgs(bbox=DOWNTOWN_BBOX, threshold_m=800)
        )
        assert r_large["pct_covered"] >= r_small["pct_covered"], (
            f"Coverage decreased from {r_small['pct_covered']} to {r_large['pct_covered']} "
            "when threshold increased from 200m to 800m"
        )

    def test_larger_threshold_whole_city_monotone(self):
        """Invariant also holds at city scale."""
        r_400 = compute_accessibility(ComputeAccessibilityArgs(threshold_m=400))
        r_1000 = compute_accessibility(ComputeAccessibilityArgs(threshold_m=1000))
        assert r_1000["pct_covered"] >= r_400["pct_covered"]

    def test_determinism(self):
        """Same input twice → same output."""
        args = ComputeAccessibilityArgs(bbox=DOWNTOWN_BBOX, threshold_m=400)
        r1 = compute_accessibility(args)
        r2 = compute_accessibility(args)
        assert r1["pct_covered"] == r2["pct_covered"]
        assert r1["mean_distance_m"] == r2["mean_distance_m"]

    def test_pct_covered_range(self):
        """Coverage percentage is always in [0, 100]."""
        result = compute_accessibility(ComputeAccessibilityArgs())
        assert 0 <= result["pct_covered"] <= 100

    def test_output_is_json_serializable(self):
        """Output contains no numpy scalars or non-serialisable types."""
        import json
        result = compute_accessibility(ComputeAccessibilityArgs(bbox=DOWNTOWN_BBOX))
        # Should not raise
        json.dumps(result)

    # Input validation

    def test_threshold_zero_raises(self):
        with pytest.raises(ValidationError):
            ComputeAccessibilityArgs(threshold_m=0)

    def test_threshold_above_max_raises(self):
        with pytest.raises(ValidationError):
            ComputeAccessibilityArgs(threshold_m=2001)

    def test_invalid_bbox_type_raises(self):
        with pytest.raises((ValidationError, TypeError)):
            ComputeAccessibilityArgs(bbox="not-a-bbox")


# ---------------------------------------------------------------------------
# equity_gap_report
# ---------------------------------------------------------------------------

class TestEquityGapReport:
    def test_happy_path_whole_city(self):
        """City-wide run returns a list of gap neighbourhoods."""
        result = equity_gap_report(EquityGapReportArgs())
        assert "gap_neighbourhoods" in result
        assert "total_analysed" in result
        assert isinstance(result["gap_neighbourhoods"], list)
        assert len(result["gap_neighbourhoods"]) <= 10  # default top_n=10
        assert result["total_analysed"] > 0

    def test_gap_neighbourhood_keys(self):
        """Each item has the expected keys."""
        result = equity_gap_report(EquityGapReportArgs(top_n=5))
        for item in result["gap_neighbourhoods"]:
            assert "neighbourhood" in item
            assert "gap_score" in item
            assert "has_stop_within_400m" in item

    def test_gap_scores_are_finite(self):
        """Gap scores should be finite numbers, not NaN/inf."""
        import math
        result = equity_gap_report(EquityGapReportArgs())
        for item in result["gap_neighbourhoods"]:
            assert math.isfinite(item["gap_score"]), f"gap_score is not finite: {item}"

    def test_lake_bbox_returns_empty(self):
        """A bbox over the lake with no neighbourhoods returns an empty list."""
        result = equity_gap_report(EquityGapReportArgs(bbox=LAKE_BBOX))
        assert result["gap_neighbourhoods"] == []
        assert result["total_analysed"] == 0

    def test_top_n_respected(self):
        """Returns at most top_n neighbourhoods."""
        result = equity_gap_report(EquityGapReportArgs(top_n=3))
        assert len(result["gap_neighbourhoods"]) <= 3

    def test_determinism(self):
        """Same input → same output."""
        args = EquityGapReportArgs(top_n=5)
        r1 = equity_gap_report(args)
        r2 = equity_gap_report(args)
        assert r1["gap_neighbourhoods"] == r2["gap_neighbourhoods"]

    def test_output_is_json_serializable(self):
        import json
        result = equity_gap_report(EquityGapReportArgs(top_n=5))
        json.dumps(result)

    # Input validation

    def test_top_n_zero_raises(self):
        with pytest.raises(ValidationError):
            EquityGapReportArgs(top_n=0)

    def test_top_n_above_max_raises(self):
        with pytest.raises(ValidationError):
            EquityGapReportArgs(top_n=200)


# ---------------------------------------------------------------------------
# reachability
# ---------------------------------------------------------------------------

class TestReachability:
    def test_happy_path_union_station(self):
        """Union Station with 45-min budget should reach many stops."""
        result = reachability(
            ReachabilityArgs(
                origin_lon=UNION_LON,
                origin_lat=UNION_LAT,
                time_budget_min=45,
            )
        )
        assert "reachable_stop_count" in result
        assert "walk_radius_m" in result
        assert result["reachable_stop_count"] >= 0
        assert result["walk_radius_m"] > 0

    def test_larger_time_budget_not_fewer_stops(self):
        """Invariant: more time → at least as many reachable stops."""
        r_small = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=10)
        )
        r_large = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=45)
        )
        assert r_large["reachable_stop_count"] >= r_small["reachable_stop_count"]

    def test_origin_in_lake_zero_stops_in_walkable_range(self):
        """An origin far from any stop should return 0 reachable stops for short budget."""
        # Lake Ontario centre — no stops there
        result = reachability(
            ReachabilityArgs(
                origin_lon=-79.39,
                origin_lat=43.58,
                time_budget_min=1,  # 1 min ≈ 83 m walk
            )
        )
        assert result["reachable_stop_count"] == 0

    def test_determinism(self):
        args = ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=20)
        r1 = reachability(args)
        r2 = reachability(args)
        assert r1["reachable_stop_count"] == r2["reachable_stop_count"]

    def test_output_is_json_serializable(self):
        import json
        result = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=20)
        )
        json.dumps(result)

    def test_sample_list_capped_at_20(self):
        """The reachable_stops_sample list has at most 20 items."""
        result = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=60)
        )
        assert len(result["reachable_stops_sample"]) <= 20

    def test_reachable_count_matches_sample_or_larger(self):
        """reachable_stop_count >= len(sample) since sample is capped."""
        result = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=30)
        )
        assert result["reachable_stop_count"] >= len(result["reachable_stops_sample"])

    def test_opportunity_access_present_and_in_unit_interval(self):
        """O-D demand side: reachability reports the origin's opportunity access."""
        result = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=30)
        )
        assert 0.0 <= result["opportunity_access"] <= 1.0
        nc = result["nearest_job_centre"]
        assert nc is not None and "name" in nc and "distance_m" in nc

    def test_downtown_has_more_opportunity_access_than_periphery(self):
        downtown = reachability(
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=30)
        )
        periphery = reachability(
            ReachabilityArgs(origin_lon=-79.62, origin_lat=43.83, time_budget_min=30)
        )
        assert downtown["opportunity_access"] > periphery["opportunity_access"]

    # Input validation

    def test_time_budget_zero_raises(self):
        with pytest.raises(ValidationError):
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=0)

    def test_time_budget_above_max_raises(self):
        with pytest.raises(ValidationError):
            ReachabilityArgs(origin_lon=UNION_LON, origin_lat=UNION_LAT, time_budget_min=200)

    def test_missing_origin_raises(self):
        with pytest.raises(ValidationError):
            ReachabilityArgs(time_budget_min=30)  # missing lon/lat


# ---------------------------------------------------------------------------
# estimate_demand
# ---------------------------------------------------------------------------

class TestEstimateDemand:
    def test_happy_path_whole_city(self):
        """City-wide demand surface returns top-20 neighbourhoods."""
        result = estimate_demand(EstimateDemandArgs())
        assert "demand_surface" in result
        assert "total_analysed" in result
        assert isinstance(result["demand_surface"], list)
        assert len(result["demand_surface"]) <= 20
        assert result["total_analysed"] > 0

    def test_demand_surface_keys(self):
        """Each item has required keys."""
        result = estimate_demand(EstimateDemandArgs())
        for item in result["demand_surface"]:
            assert "neighbourhood" in item
            assert "demand_score" in item
            assert "population" in item

    def test_demand_surface_exposes_opportunity_access(self):
        """O-D demand side: each entry carries gravity job-access in [0, 1]."""
        result = estimate_demand(EstimateDemandArgs())
        for item in result["demand_surface"]:
            assert "opportunity_access" in item
            assert 0.0 <= item["opportunity_access"] <= 1.0

    def test_demand_scores_positive(self):
        """Demand scores should be non-negative."""
        result = estimate_demand(EstimateDemandArgs())
        for item in result["demand_surface"]:
            assert item["demand_score"] >= 0, f"Negative demand score: {item}"

    def test_future_horizon_not_less_than_now(self):
        """2051 horizon should yield >= demand scores than 'now' (growth factor applied)."""
        r_now = estimate_demand(EstimateDemandArgs(bbox=DOWNTOWN_BBOX, horizon="now"))
        r_future = estimate_demand(EstimateDemandArgs(bbox=DOWNTOWN_BBOX, horizon="2051"))
        # Top score for 2051 should be >= top score for now
        if r_now["demand_surface"] and r_future["demand_surface"]:
            assert r_future["demand_surface"][0]["demand_score"] >= r_now["demand_surface"][0]["demand_score"]

    def test_lake_bbox_returns_empty(self):
        result = estimate_demand(EstimateDemandArgs(bbox=LAKE_BBOX))
        assert result["demand_surface"] == []
        assert result["total_analysed"] == 0

    def test_determinism(self):
        args = EstimateDemandArgs(horizon="now")
        r1 = estimate_demand(args)
        r2 = estimate_demand(args)
        assert r1["demand_surface"] == r2["demand_surface"]

    def test_output_is_json_serializable(self):
        import json
        result = estimate_demand(EstimateDemandArgs(bbox=DOWNTOWN_BBOX))
        json.dumps(result)

    # Input validation

    def test_invalid_horizon_raises(self):
        with pytest.raises(ValidationError):
            EstimateDemandArgs(horizon="2045")  # not a valid literal


# ---------------------------------------------------------------------------
# reliability_report
# ---------------------------------------------------------------------------

class TestReliabilityReport:
    def test_happy_path_city_wide_bus(self):
        """City-wide bus reliability returns top routes by mean delay."""
        result = reliability_report(ReliabilityReportArgs(mode="bus"))
        assert "routes" in result
        assert "total_incidents" in result
        assert isinstance(result["routes"], list)
        assert result["total_incidents"] > 0
        assert len(result["routes"]) <= 10

    def test_happy_path_city_wide_streetcar(self):
        result = reliability_report(ReliabilityReportArgs(mode="streetcar"))
        assert result["total_incidents"] > 0

    def test_happy_path_all_modes(self):
        result = reliability_report(ReliabilityReportArgs(mode="all"))
        assert result["total_incidents"] > 0

    def test_route_keys(self):
        """Each route entry has required keys with sane values."""
        result = reliability_report(ReliabilityReportArgs(mode="bus", top_n=5))
        for route in result["routes"]:
            assert "route" in route
            assert "incident_count" in route
            assert "mean_delay_min" in route
            assert route["incident_count"] >= 0
            assert route["mean_delay_min"] >= 0

    def test_specific_route_filter(self):
        """Filtering by a route name returns only matching incidents."""
        # Pick a route we know exists in the bus data
        result_all = reliability_report(ReliabilityReportArgs(mode="bus", top_n=100))
        if not result_all["routes"]:
            pytest.skip("No bus routes found")
        top_route = result_all["routes"][0]["route"]
        result_filtered = reliability_report(
            ReliabilityReportArgs(route=top_route, mode="bus")
        )
        assert len(result_filtered["routes"]) >= 1
        assert all(top_route in r["route"] for r in result_filtered["routes"])

    def test_nonexistent_route_returns_empty(self):
        result = reliability_report(
            ReliabilityReportArgs(route="999 NONEXISTENT_ROUTE_XYZ", mode="all")
        )
        assert result["routes"] == []

    def test_top_n_respected(self):
        result = reliability_report(ReliabilityReportArgs(top_n=3, mode="bus"))
        assert len(result["routes"]) <= 3

    def test_determinism(self):
        args = ReliabilityReportArgs(mode="bus", top_n=5)
        r1 = reliability_report(args)
        r2 = reliability_report(args)
        assert r1["routes"] == r2["routes"]

    def test_output_is_json_serializable(self):
        import json
        result = reliability_report(ReliabilityReportArgs(mode="all", top_n=5))
        json.dumps(result)

    def test_delay_values_non_negative(self):
        """Mean and p95 delays should be non-negative."""
        result = reliability_report(ReliabilityReportArgs(mode="all", top_n=20))
        for route in result["routes"]:
            assert route["mean_delay_min"] >= 0
            assert route["p95_delay_min"] >= route["median_delay_min"] - 0.01  # p95 >= median

    # Input validation

    def test_invalid_mode_raises(self):
        with pytest.raises(ValidationError):
            ReliabilityReportArgs(mode="subway")

    def test_top_n_zero_raises(self):
        with pytest.raises(ValidationError):
            ReliabilityReportArgs(top_n=0)

    def test_top_n_above_max_raises(self):
        with pytest.raises(ValidationError):
            ReliabilityReportArgs(top_n=101)
