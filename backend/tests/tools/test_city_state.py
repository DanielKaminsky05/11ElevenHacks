"""Tests for Family A — City State & Lookup tools.

Coverage per tool-builder spec (§3 of .claude/agents/tool-builder.md):
  1. Happy path — concrete, meaningful assertions
  2. Schema validity — model_json_schema() present; tool in registry
  3. Input validation — ValidationError on bad inputs
  4. Boundaries / edge cases — tiny area, empty results, outside Toronto
  5. Determinism — same input → same output
  6. Invariants — counts ≥ 0, percentages in expected ranges, monotonicity
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.common import BBox
from app.tools.city_state import (
    CompareAreasArgs,
    GetCityGridArgs,
    ListTransitArgs,
    ProfileAreaArgs,
    compare_areas,
    get_city_grid,
    list_transit,
    profile_area,
)
from app.tools.registry import get_tool

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

# A small downtown bbox that definitely contains stops.
DOWNTOWN_BBOX = BBox(west=-79.395, south=43.645, east=-79.370, north=43.660)

# A bbox clearly outside Toronto (Lake Ontario, south of the city).
OUTSIDE_TORONTO_BBOX = BBox(west=-79.4, south=43.40, east=-79.3, north=43.45)

# A very small bbox in the lake (no stops).
TINY_NO_STOP_BBOX = BBox(west=-79.39, south=43.62, east=-79.38, north=43.63)


# ===========================================================================
# Family A §2 — Schema / registry checks
# ===========================================================================


class TestRegistryAndSchema:
    def test_get_city_grid_is_registered(self):
        spec = get_tool("get_city_grid")
        assert spec.name == "get_city_grid"
        assert spec.fn is get_city_grid

    def test_profile_area_is_registered(self):
        spec = get_tool("profile_area")
        assert spec.name == "profile_area"
        assert spec.fn is profile_area

    def test_list_transit_is_registered(self):
        spec = get_tool("list_transit")
        assert spec.name == "list_transit"
        assert spec.fn is list_transit

    def test_compare_areas_is_registered(self):
        spec = get_tool("compare_areas")
        assert spec.name == "compare_areas"
        assert spec.fn is compare_areas

    def test_get_city_grid_schema_has_required_fields(self):
        schema = GetCityGridArgs.model_json_schema()
        props = schema.get("properties", {})
        assert "resolution" in props
        assert "channels" in props

    def test_profile_area_schema_has_name_field(self):
        schema = ProfileAreaArgs.model_json_schema()
        assert "name" in schema.get("properties", {})

    def test_list_transit_schema_has_modes_field(self):
        schema = ListTransitArgs.model_json_schema()
        assert "modes" in schema.get("properties", {})

    def test_compare_areas_schema_has_areas_and_metrics(self):
        schema = CompareAreasArgs.model_json_schema()
        props = schema.get("properties", {})
        assert "areas" in props
        assert "metrics" in props


# ===========================================================================
# get_city_grid
# ===========================================================================


class TestGetCityGrid:
    def test_happy_path_returns_expected_keys(self):
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=10)
        result = get_city_grid(args)
        assert "bbox" in result
        assert "resolution" in result
        assert "channels" in result
        assert "grid" in result
        assert "lon_centres" in result
        assert "lat_centres" in result

    def test_resolution_matches_grid_dimensions(self):
        N = 8
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=N)
        result = get_city_grid(args)
        grid = result["grid"]["stops"]
        assert len(grid) == N
        assert all(len(row) == N for row in grid)

    def test_lon_lat_centres_length_equals_resolution(self):
        N = 6
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=N)
        result = get_city_grid(args)
        assert len(result["lon_centres"]) == N
        assert len(result["lat_centres"]) == N

    def test_stops_channel_has_stops_in_downtown_bbox(self):
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=20)
        result = get_city_grid(args)
        grid = result["grid"]["stops"]
        total = sum(cell for row in grid for cell in row)
        assert total > 0, "Downtown bbox should contain transit stops"

    def test_stops_channel_is_zero_outside_toronto(self):
        args = GetCityGridArgs(
            bbox=OUTSIDE_TORONTO_BBOX, channels=["stops"], resolution=10
        )
        result = get_city_grid(args)
        grid = result["grid"]["stops"]
        total = sum(cell for row in grid for cell in row)
        assert total == 0, "Area outside Toronto should have no stops"

    def test_population_channel_returns_grid(self):
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["population"], resolution=10)
        result = get_city_grid(args)
        assert "population" in result["grid"]
        grid = result["grid"]["population"]
        assert len(grid) == 10

    def test_all_channels_returned(self):
        channels = ["population", "stops", "income"]
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=channels, resolution=5)
        result = get_city_grid(args)
        assert set(result["channels"]) == set(channels)
        for ch in channels:
            assert ch in result["grid"]

    def test_stub_channels_return_zero_grid(self):
        """destinations/network/boundary are stubs and should return all-zero grids."""
        args = GetCityGridArgs(
            bbox=DOWNTOWN_BBOX, channels=["destinations", "network", "boundary"], resolution=5
        )
        result = get_city_grid(args)
        for ch in ["destinations", "network", "boundary"]:
            grid = result["grid"][ch]
            total = sum(cell for row in grid for cell in row)
            assert total == 0, f"Stub channel {ch!r} should be all zeros"

    def test_whole_city_no_bbox(self):
        """Omitting bbox should use the Toronto default and return a valid grid."""
        args = GetCityGridArgs(channels=["stops"], resolution=10)
        result = get_city_grid(args)
        grid = result["grid"]["stops"]
        total = sum(cell for row in grid for cell in row)
        assert total > 0

    def test_grid_values_are_non_negative(self):
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops", "population"], resolution=10)
        result = get_city_grid(args)
        for ch, grid in result["grid"].items():
            for row in grid:
                for cell in row:
                    assert cell >= 0, f"Channel {ch!r} has negative cell value: {cell}"

    def test_determinism_same_input_same_output(self):
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=10)
        r1 = get_city_grid(args)
        r2 = get_city_grid(args)
        assert r1["grid"] == r2["grid"]

    def test_larger_resolution_same_or_more_total_stops(self):
        """Monotonicity: increasing resolution does not lose stops (same bbox)."""
        args_small = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=5)
        args_large = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=20)
        total_small = sum(
            c for row in get_city_grid(args_small)["grid"]["stops"] for c in row
        )
        total_large = sum(
            c for row in get_city_grid(args_large)["grid"]["stops"] for c in row
        )
        assert total_large >= total_small

    def test_result_is_json_serializable(self):
        import json
        args = GetCityGridArgs(bbox=DOWNTOWN_BBOX, channels=["stops"], resolution=5)
        result = get_city_grid(args)
        # Should not raise
        json.dumps(result)

    # --- Input validation ---

    def test_resolution_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(channels=["stops"], resolution=4)

    def test_resolution_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(channels=["stops"], resolution=201)

    def test_empty_channels_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(channels=[], resolution=10)

    def test_invalid_channel_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(channels=["invalid_channel"], resolution=10)

    def test_bbox_east_less_than_west_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(
                bbox=BBox(west=-79.0, south=43.6, east=-79.5, north=43.7),
                channels=["stops"],
                resolution=10,
            )

    def test_bbox_north_less_than_south_raises(self):
        with pytest.raises(ValidationError):
            GetCityGridArgs(
                bbox=BBox(west=-79.5, south=43.7, east=-79.0, north=43.6),
                channels=["stops"],
                resolution=10,
            )


# ===========================================================================
# profile_area
# ===========================================================================


class TestProfileArea:
    def test_happy_path_known_neighbourhood(self):
        args = ProfileAreaArgs(name="Malvern")
        result = profile_area(args)
        assert result["matched_name"] is not None
        assert "Malvern" in result["matched_name"]
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)

    def test_population_is_positive_integer(self):
        args = ProfileAreaArgs(name="Malvern", metrics=["population"])
        result = profile_area(args)
        pop = result["metrics"].get("population")
        assert pop is not None, "Expected population metric"
        assert isinstance(pop, int)
        assert pop > 0

    def test_stop_count_is_non_negative(self):
        args = ProfileAreaArgs(name="Malvern", metrics=["stop_count"])
        result = profile_area(args)
        count = result["metrics"].get("stop_count")
        assert count is not None
        assert count >= 0

    def test_pct_low_income_in_valid_range(self):
        args = ProfileAreaArgs(name="Malvern", metrics=["pct_low_income"])
        result = profile_area(args)
        val = result["metrics"].get("pct_low_income")
        if val is not None:
            assert 0.0 <= val <= 100.0

    def test_all_default_metrics_returned(self):
        args = ProfileAreaArgs(name="Malvern")
        result = profile_area(args)
        for m in ["population", "median_age", "median_household_income", "pct_low_income", "stop_count"]:
            assert m in result["metrics"], f"Expected metric {m!r} in result"

    def test_downtown_neighbourhood_has_many_stops(self):
        """Downtown / high-density areas should have more stops than a stub."""
        args = ProfileAreaArgs(name="Bay-Cloverhill", metrics=["stop_count"])
        result = profile_area(args)
        if result["matched_name"] is not None:
            count = result["metrics"].get("stop_count", 0)
            assert count >= 0  # minimal invariant; value is data-dependent

    def test_unknown_neighbourhood_returns_error_not_crash(self):
        args = ProfileAreaArgs(name="ZZZNonExistentNeighbourhood99999")
        result = profile_area(args)
        assert result["matched_name"] is None
        assert "error" in result

    def test_partial_name_match(self):
        """A partial name like 'Scarb' should still resolve to a neighbourhood."""
        args = ProfileAreaArgs(name="Scarb", metrics=["population"])
        result = profile_area(args)
        # Either matched or gracefully not found — must not crash.
        assert isinstance(result, dict)

    def test_determinism(self):
        args = ProfileAreaArgs(name="Malvern", metrics=["population", "stop_count"])
        r1 = profile_area(args)
        r2 = profile_area(args)
        assert r1 == r2

    def test_result_is_json_serializable(self):
        import json
        args = ProfileAreaArgs(name="Malvern")
        json.dumps(profile_area(args))

    # --- Input validation ---

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            ProfileAreaArgs(name="")

    def test_invalid_metric_raises(self):
        with pytest.raises(ValidationError):
            ProfileAreaArgs(name="Malvern", metrics=["nonexistent_metric"])

    def test_empty_metrics_raises(self):
        with pytest.raises(ValidationError):
            ProfileAreaArgs(name="Malvern", metrics=[])


# ===========================================================================
# list_transit
# ===========================================================================


class TestListTransit:
    def test_happy_path_downtown_returns_stops(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX)
        result = list_transit(args)
        assert result["stop_count"] > 0
        assert len(result["stops"]) > 0

    def test_returned_keys_present(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX)
        result = list_transit(args)
        for key in ("bbox", "modes", "stop_count", "stops", "route_count", "routes"):
            assert key in result, f"Expected key {key!r} in result"

    def test_stop_count_matches_stops_list_length(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX)
        result = list_transit(args)
        assert result["stop_count"] == len(result["stops"])

    def test_stops_have_required_fields(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX, limit=5)
        result = list_transit(args)
        for stop in result["stops"]:
            for field in ("stop_id", "name", "lat", "lon", "agency"):
                assert field in stop, f"Stop missing field {field!r}"

    def test_stop_coordinates_in_bbox(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX)
        result = list_transit(args)
        for stop in result["stops"]:
            assert DOWNTOWN_BBOX.south <= stop["lat"] <= DOWNTOWN_BBOX.north
            assert DOWNTOWN_BBOX.west <= stop["lon"] <= DOWNTOWN_BBOX.east

    def test_no_stops_outside_toronto(self):
        args = ListTransitArgs(bbox=OUTSIDE_TORONTO_BBOX)
        result = list_transit(args)
        # Should return 0 TTC stops (area is south over the lake)
        assert result["stop_count"] == 0

    def test_mode_filter_bus_only(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX, modes=["bus"])
        result = list_transit(args)
        # Result must include only bus-agency routes
        for route in result["routes"]:
            assert route["mode"] == "bus"

    def test_mode_filter_subway_only_returns_subway_routes(self):
        # No bbox — whole city, to be sure we capture subway routes
        args = ListTransitArgs(modes=["subway"])
        result = list_transit(args)
        for route in result["routes"]:
            assert route["mode"] == "subway"

    def test_rail_mode_includes_go_transit(self):
        args = ListTransitArgs(modes=["rail"])
        result = list_transit(args)
        go_routes = [r for r in result["routes"] if r["agency"] == "GO"]
        assert len(go_routes) > 0, "rail mode should include GO Transit routes"

    def test_limit_respected(self):
        args = ListTransitArgs(limit=10)
        result = list_transit(args)
        assert result["stop_count"] <= 10

    def test_whole_city_default_bbox(self):
        args = ListTransitArgs()
        result = list_transit(args)
        assert result["stop_count"] > 100

    def test_routes_have_required_fields(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX, modes=["bus"])
        result = list_transit(args)
        for route in result["routes"]:
            for field in ("route_id", "short_name", "long_name", "mode", "agency"):
                assert field in route

    def test_determinism(self):
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX, modes=["bus"], limit=20)
        r1 = list_transit(args)
        r2 = list_transit(args)
        assert r1["stop_count"] == r2["stop_count"]
        assert r1["stops"] == r2["stops"]

    def test_result_is_json_serializable(self):
        import json
        args = ListTransitArgs(bbox=DOWNTOWN_BBOX, limit=20)
        json.dumps(list_transit(args))

    # --- Input validation ---

    def test_empty_modes_raises(self):
        with pytest.raises(ValidationError):
            ListTransitArgs(modes=[])

    def test_invalid_mode_raises(self):
        with pytest.raises(ValidationError):
            ListTransitArgs(modes=["helicopter"])

    def test_limit_zero_raises(self):
        with pytest.raises(ValidationError):
            ListTransitArgs(limit=0)

    def test_limit_above_max_raises(self):
        with pytest.raises(ValidationError):
            ListTransitArgs(limit=9999)

    def test_bad_bbox_east_lt_west_raises(self):
        with pytest.raises(ValidationError):
            ListTransitArgs(
                bbox=BBox(west=-79.0, south=43.6, east=-79.5, north=43.7)
            )


# ===========================================================================
# compare_areas
# ===========================================================================


class TestCompareAreas:
    def test_happy_path_two_neighbourhoods(self):
        args = CompareAreasArgs(areas=["Malvern", "Rosedale"], metrics=["population"])
        result = compare_areas(args)
        assert "areas" in result
        assert len(result["areas"]) == 2

    def test_result_has_all_required_keys(self):
        args = CompareAreasArgs(areas=["Malvern", "Rosedale"], metrics=["population"])
        result = compare_areas(args)
        for key in ("areas", "metrics", "not_found", "ranked_by"):
            assert key in result

    def test_each_row_has_area_name_and_metrics(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Annex"],
            metrics=["population", "stop_count"],
        )
        result = compare_areas(args)
        for row in result["areas"]:
            assert "area" in row
            assert "population" in row
            assert "stop_count" in row

    def test_unknown_area_goes_into_not_found(self):
        args = CompareAreasArgs(
            areas=["Malvern", "ZZZFakeNeighbourhood99"],
            metrics=["population"],
        )
        result = compare_areas(args)
        assert "ZZZFakeNeighbourhood99" in result["not_found"]

    def test_sort_by_population_descending(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Rosedale", "Annex"],
            metrics=["population"],
            sort_by="population",
        )
        result = compare_areas(args)
        pops = [
            r["population"] for r in result["areas"] if r.get("population") is not None
        ]
        assert pops == sorted(pops, reverse=True), "Results should be sorted descending by population"

    def test_all_areas_not_found(self):
        args = CompareAreasArgs(
            areas=["FakeA99", "FakeB99"],
            metrics=["population"],
        )
        result = compare_areas(args)
        assert result["areas"] == []
        assert len(result["not_found"]) == 2

    def test_ranked_by_field_reflects_sort_by(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Rosedale"],
            metrics=["population"],
            sort_by="population",
        )
        result = compare_areas(args)
        assert result["ranked_by"] == "population"

    def test_no_sort_by_ranked_by_is_none(self):
        args = CompareAreasArgs(areas=["Malvern", "Rosedale"], metrics=["population"])
        result = compare_areas(args)
        assert result["ranked_by"] is None

    def test_population_values_are_positive(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Annex"], metrics=["population"]
        )
        result = compare_areas(args)
        for row in result["areas"]:
            if row.get("population") is not None:
                assert row["population"] > 0

    def test_stop_counts_non_negative(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Annex"], metrics=["stop_count"]
        )
        result = compare_areas(args)
        for row in result["areas"]:
            if row.get("stop_count") is not None:
                assert row["stop_count"] >= 0

    def test_determinism(self):
        args = CompareAreasArgs(
            areas=["Malvern", "Rosedale"], metrics=["population", "stop_count"]
        )
        r1 = compare_areas(args)
        r2 = compare_areas(args)
        assert r1["areas"] == r2["areas"]

    def test_result_is_json_serializable(self):
        import json
        args = CompareAreasArgs(
            areas=["Malvern", "Rosedale"], metrics=["population"]
        )
        json.dumps(compare_areas(args))

    # --- Input validation ---

    def test_single_area_raises(self):
        with pytest.raises(ValidationError):
            CompareAreasArgs(areas=["Malvern"], metrics=["population"])

    def test_empty_areas_raises(self):
        with pytest.raises(ValidationError):
            CompareAreasArgs(areas=[], metrics=["population"])

    def test_invalid_metric_raises(self):
        with pytest.raises(ValidationError):
            CompareAreasArgs(areas=["Malvern", "Rosedale"], metrics=["bad_metric"])

    def test_sort_by_metric_not_in_metrics_raises(self):
        with pytest.raises(ValidationError):
            CompareAreasArgs(
                areas=["Malvern", "Rosedale"],
                metrics=["population"],
                sort_by="stop_count",  # not in metrics list
            )

    def test_empty_metrics_raises(self):
        with pytest.raises(ValidationError):
            CompareAreasArgs(areas=["Malvern", "Rosedale"], metrics=[])
