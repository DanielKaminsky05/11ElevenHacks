"""Tests for Family C — Scenario Simulation tools.

Covers: simulate_change, diff_scenarios, constraint_check.

Run with:
    cd backend && ./.venv/Scripts/python.exe -m pytest tests/tools/test_simulation.py -q
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tools.registry import get_tool
from app.tools.simulation import (
    ConstraintCheckArgs,
    DiffScenariosArgs,
    ScenarioLayout,
    SimulateChangeArgs,
    constraint_check,
    diff_scenarios,
    simulate_change,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# A stop that definitely exists in the TTC GTFS data
_KNOWN_STOP_ID = "662"  # Danforth Rd at Kennedy Rd (stop_id 662 from TTC GTFS)
_KNOWN_LAT = 43.714379
_KNOWN_LON = -79.260939

# A location inside Toronto (near downtown)
_TORONTO_LON = -79.38
_TORONTO_LAT = 43.65

# A small set of stops for diff_scenarios tests
def _make_small_layout(n: int = 5, label: str = "test") -> dict:
    """Return a ScenarioLayout dict with n stops near downtown Toronto."""
    stops = [
        {
            "stop_id": f"test_{i}",
            "lat": 43.65 + i * 0.005,
            "lon": -79.38 + i * 0.005,
        }
        for i in range(n)
    ]
    return {"stops": stops, "label": label}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_simulate_change_registered_in_registry():
    spec = get_tool("simulate_change")
    assert spec.name == "simulate_change"
    assert spec.fn is simulate_change


def test_diff_scenarios_registered_in_registry():
    spec = get_tool("diff_scenarios")
    assert spec.name == "diff_scenarios"
    assert spec.fn is diff_scenarios


def test_constraint_check_registered_in_registry():
    spec = get_tool("constraint_check")
    assert spec.name == "constraint_check"
    assert spec.fn is constraint_check


def test_simulate_change_has_json_schema():
    schema = SimulateChangeArgs.model_json_schema()
    assert "properties" in schema
    assert "operations" in schema["properties"]


def test_diff_scenarios_has_json_schema():
    schema = DiffScenariosArgs.model_json_schema()
    assert "properties" in schema


def test_constraint_check_has_json_schema():
    schema = ConstraintCheckArgs.model_json_schema()
    assert "properties" in schema
    assert "layout" in schema["properties"]


# ---------------------------------------------------------------------------
# simulate_change — happy path
# ---------------------------------------------------------------------------


def test_simulate_change_empty_operations_before_equals_after():
    """Empty operations list: before and after metrics must be identical."""
    args = SimulateChangeArgs(operations=[])
    result = simulate_change(args)

    assert result["before"]["stop_count"] == result["after"]["stop_count"]
    assert result["before"]["pct_covered"] == result["after"]["pct_covered"]
    assert result["before"]["equity_weighted_access"] == result["after"]["equity_weighted_access"]
    assert result["delta"]["pct_covered"] == 0.0
    assert result["ops_applied"] == 0
    assert result["warnings"] == []


def test_simulate_change_output_keys_present():
    args = SimulateChangeArgs(operations=[])
    result = simulate_change(args)

    for key in ("before", "after", "delta", "winners_losers", "warnings", "ops_applied"):
        assert key in result, f"Missing key: {key}"

    for section in ("before", "after"):
        for metric in ("stop_count", "pct_covered", "mean_walk_distance_m", "equity_weighted_access"):
            assert metric in result[section], f"Missing {metric} in {section}"

    for key in ("winners", "losers", "unchanged"):
        assert key in result["winners_losers"], f"Missing winners_losers.{key}"


def test_simulate_change_coverage_in_valid_range():
    args = SimulateChangeArgs(operations=[])
    result = simulate_change(args)

    assert 0.0 <= result["before"]["pct_covered"] <= 1.0
    assert 0.0 <= result["after"]["pct_covered"] <= 1.0
    assert 0.0 <= result["before"]["equity_weighted_access"] <= 1.0
    assert 0.0 <= result["after"]["equity_weighted_access"] <= 1.0


def test_simulate_change_add_stop_increases_or_maintains_stop_count():
    args = SimulateChangeArgs(
        operations=[
            {
                "op": "add_stop",
                "stop_id": "new_test_001",
                "coord": {"lon": _TORONTO_LON, "lat": _TORONTO_LAT},
            }
        ]
    )
    result = simulate_change(args)

    assert result["after"]["stop_count"] == result["before"]["stop_count"] + 1
    assert result["ops_applied"] == 1


def test_simulate_change_remove_existing_stop_decreases_count():
    """Removing a known stop should reduce stop count by 1."""
    args = SimulateChangeArgs(
        operations=[
            {"op": "remove_stop", "stop_id": _KNOWN_STOP_ID}
        ]
    )
    result = simulate_change(args)

    assert result["after"]["stop_count"] == result["before"]["stop_count"] - 1
    assert result["warnings"] == []


def test_simulate_change_remove_nonexistent_stop_warns_not_crashes():
    """Removing a stop that doesn't exist should produce a warning, not an error."""
    args = SimulateChangeArgs(
        operations=[
            {"op": "remove_stop", "stop_id": "DOES_NOT_EXIST_XYZ"}
        ]
    )
    result = simulate_change(args)

    # Stop count should be unchanged
    assert result["after"]["stop_count"] == result["before"]["stop_count"]
    # A warning should be emitted
    assert len(result["warnings"]) == 1
    assert "DOES_NOT_EXIST_XYZ" in result["warnings"][0]


def test_simulate_change_move_stop_updates_count_unchanged():
    """Moving a stop should keep the same number of stops."""
    args = SimulateChangeArgs(
        operations=[
            {
                "op": "move_stop",
                "stop_id": _KNOWN_STOP_ID,
                "new_coord": {"lon": _TORONTO_LON, "lat": _TORONTO_LAT},
            }
        ]
    )
    result = simulate_change(args)

    assert result["after"]["stop_count"] == result["before"]["stop_count"]
    assert result["warnings"] == []


def test_simulate_change_deterministic():
    """Same input must yield same output."""
    args = SimulateChangeArgs(operations=[])
    result_1 = simulate_change(args)
    result_2 = simulate_change(args)

    assert result_1["before"]["pct_covered"] == result_2["before"]["pct_covered"]
    assert result_1["before"]["equity_weighted_access"] == result_2["before"]["equity_weighted_access"]


def test_simulate_change_winners_losers_are_lists():
    args = SimulateChangeArgs(operations=[])
    result = simulate_change(args)

    wl = result["winners_losers"]
    assert isinstance(wl["winners"], list)
    assert isinstance(wl["losers"], list)
    assert isinstance(wl["unchanged"], list)


def test_simulate_change_move_nonexistent_stop_warns():
    args = SimulateChangeArgs(
        operations=[
            {
                "op": "move_stop",
                "stop_id": "NO_SUCH_STOP",
                "new_coord": {"lon": _TORONTO_LON, "lat": _TORONTO_LAT},
            }
        ]
    )
    result = simulate_change(args)

    assert any("NO_SUCH_STOP" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# simulate_change — input validation
# ---------------------------------------------------------------------------


def test_simulate_change_invalid_buffer_too_large():
    with pytest.raises(ValidationError):
        SimulateChangeArgs(operations=[], buffer_m=5000)


def test_simulate_change_invalid_buffer_zero():
    with pytest.raises(ValidationError):
        SimulateChangeArgs(operations=[], buffer_m=0)


def test_simulate_change_invalid_op_unknown():
    with pytest.raises((ValidationError, ValueError)):
        SimulateChangeArgs(
            operations=[{"op": "teleport_stop", "stop_id": "x", "coord": {"lon": 0, "lat": 0}}]
        )


def test_simulate_change_add_stop_missing_coord():
    with pytest.raises(ValidationError):
        SimulateChangeArgs(
            operations=[{"op": "add_stop", "stop_id": "x"}]  # missing coord
        )


def test_simulate_change_add_stop_invalid_coord():
    with pytest.raises(ValidationError):
        SimulateChangeArgs(
            operations=[
                {"op": "add_stop", "stop_id": "x", "coord": {"lon": 999, "lat": 999}}
            ]
        )


# ---------------------------------------------------------------------------
# simulate_change — edge cases / invariants
# ---------------------------------------------------------------------------


def test_simulate_change_larger_buffer_never_decreases_coverage():
    """A larger walk buffer cannot produce lower coverage than a smaller one."""
    args_small = SimulateChangeArgs(operations=[], buffer_m=200)
    args_large = SimulateChangeArgs(operations=[], buffer_m=800)

    result_small = simulate_change(args_small)
    result_large = simulate_change(args_large)

    assert result_large["before"]["pct_covered"] >= result_small["before"]["pct_covered"]


def test_simulate_change_mean_walk_time_consistent_with_distance():
    """Walk time proxy = distance / 1.2 m/s."""
    args = SimulateChangeArgs(operations=[])
    result = simulate_change(args)

    dist = result["before"]["mean_walk_distance_m"]
    time = result["before"]["mean_walk_time_s"]
    if dist is not None and time is not None:
        assert abs(time - dist / 1.2) < 1.0  # within 1 second rounding


# ---------------------------------------------------------------------------
# diff_scenarios — happy path
# ---------------------------------------------------------------------------


def test_diff_scenarios_identical_layouts_zero_delta():
    """Comparing a layout to itself should produce zero deltas."""
    layout = _make_small_layout(n=5, label="A")
    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout),
        scenario_b=ScenarioLayout(**{**layout, "label": "B"}),
    )
    result = diff_scenarios(args)

    assert result["delta"]["pct_covered"] == 0.0
    assert result["delta"]["equity_weighted_access"] == 0.0
    assert result["delta"]["stops_added"] == []
    assert result["delta"]["stops_removed"] == []


def test_diff_scenarios_output_keys_present():
    layout = _make_small_layout(n=3)
    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout),
        scenario_b=ScenarioLayout(**{**layout, "label": "B"}),
    )
    result = diff_scenarios(args)

    for key in ("scenario_a", "scenario_b", "delta", "winners_losers"):
        assert key in result

    for section in ("scenario_a", "scenario_b"):
        for metric in ("label", "stop_count", "pct_covered", "equity_weighted_access"):
            assert metric in result[section]


def test_diff_scenarios_added_stops_tracked():
    layout_a = _make_small_layout(n=3, label="A")
    layout_b = _make_small_layout(n=3, label="B")
    layout_b["stops"] = layout_b["stops"] + [
        {"stop_id": "extra_stop", "lat": 43.66, "lon": -79.39}
    ]
    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout_a),
        scenario_b=ScenarioLayout(**layout_b),
    )
    result = diff_scenarios(args)

    assert "extra_stop" in result["delta"]["stops_added"]
    assert result["scenario_b"]["stop_count"] == result["scenario_a"]["stop_count"] + 1


def test_diff_scenarios_removed_stops_tracked():
    layout_a = _make_small_layout(n=4, label="A")
    layout_b = {"stops": layout_a["stops"][1:], "label": "B"}  # drop first stop

    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout_a),
        scenario_b=ScenarioLayout(**layout_b),
    )
    result = diff_scenarios(args)

    removed_id = str(layout_a["stops"][0]["stop_id"])
    assert removed_id in result["delta"]["stops_removed"]


def test_diff_scenarios_empty_layout_a_vs_some_b():
    """Empty layout A vs layout B — B should have higher coverage."""
    layout_a = {"stops": [], "label": "empty"}
    layout_b = _make_small_layout(n=5, label="real")
    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout_a),
        scenario_b=ScenarioLayout(**layout_b),
    )
    result = diff_scenarios(args)

    # Layout B has stops so coverage should be >= A (which is 0)
    assert result["scenario_a"]["pct_covered"] == 0.0
    assert result["delta"]["pct_covered"] >= 0.0


def test_diff_scenarios_coverage_in_valid_range():
    layout = _make_small_layout(n=4)
    args = DiffScenariosArgs(
        scenario_a=ScenarioLayout(**layout),
        scenario_b=ScenarioLayout(**{**layout, "label": "B"}),
    )
    result = diff_scenarios(args)

    for section in ("scenario_a", "scenario_b"):
        assert 0.0 <= result[section]["pct_covered"] <= 1.0
        assert 0.0 <= result[section]["equity_weighted_access"] <= 1.0


# ---------------------------------------------------------------------------
# diff_scenarios — input validation
# ---------------------------------------------------------------------------


def test_diff_scenarios_stop_missing_lat():
    with pytest.raises(ValidationError):
        DiffScenariosArgs(
            scenario_a=ScenarioLayout(
                stops=[{"stop_id": "x", "lon": -79.38}],  # missing lat
                label="A",
            ),
            scenario_b=ScenarioLayout(stops=[], label="B"),
        )


def test_diff_scenarios_invalid_buffer():
    layout = _make_small_layout(n=2)
    with pytest.raises(ValidationError):
        DiffScenariosArgs(
            scenario_a=ScenarioLayout(**layout),
            scenario_b=ScenarioLayout(**{**layout, "label": "B"}),
            buffer_m=0,
        )


# ---------------------------------------------------------------------------
# constraint_check — happy path
# ---------------------------------------------------------------------------


def test_constraint_check_well_spaced_toronto_stops_feasible():
    """Four well-spaced stops inside Toronto with generous budget — should pass."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "c1", "lat": 43.64, "lon": -79.38},
                {"stop_id": "c2", "lat": 43.65, "lon": -79.40},
                {"stop_id": "c3", "lat": 43.66, "lon": -79.42},
                {"stop_id": "c4", "lat": 43.67, "lon": -79.44},
            ]
        },
        min_spacing_m=100,
        max_route_distance_m=5000,  # very generous → no route violations
        stop_budget=10,
        check_toronto_boundary=True,
    )
    result = constraint_check(args)

    assert result["stop_count"] == 4
    assert result["budget_ok"] is True
    # Spacing: consecutive stops are ~200 m apart — should not trigger at 100 m
    spacing_viols = [v for v in result["violations"] if v["type"] == "stops_too_close"]
    assert len(spacing_viols) == 0


def test_constraint_check_output_keys_present():
    args = ConstraintCheckArgs(
        layout={"stops": [{"stop_id": "x", "lat": 43.65, "lon": -79.38}]},
        min_spacing_m=150,
        stop_budget=5,
    )
    result = constraint_check(args)

    for key in ("feasible", "stop_count", "budget_ok", "violations", "violation_count", "stops"):
        assert key in result


def test_constraint_check_budget_exceeded():
    """More stops than budget → budget violation."""
    stops = [{"stop_id": f"s{i}", "lat": 43.64 + i * 0.01, "lon": -79.38} for i in range(5)]
    args = ConstraintCheckArgs(
        layout={"stops": stops},
        stop_budget=3,
        min_spacing_m=50,
        max_route_distance_m=5000,
    )
    result = constraint_check(args)

    assert result["budget_ok"] is False
    budget_viols = [v for v in result["violations"] if v["type"] == "stop_budget_exceeded"]
    assert len(budget_viols) == 1
    assert result["feasible"] is False


def test_constraint_check_stops_too_close():
    """Two stops 30 m apart with min_spacing_m=150 → spacing violation."""
    # 30 m ≈ 0.00027 degrees latitude
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "near_a", "lat": 43.6500, "lon": -79.3800},
                {"stop_id": "near_b", "lat": 43.6502, "lon": -79.3800},  # ~22 m
            ]
        },
        min_spacing_m=150,
        max_route_distance_m=5000,
        stop_budget=10,
    )
    result = constraint_check(args)

    spacing_viols = [v for v in result["violations"] if v["type"] == "stops_too_close"]
    assert len(spacing_viols) >= 1
    assert result["feasible"] is False


def test_constraint_check_outside_toronto_flagged():
    """A stop in New York should be flagged as outside Toronto."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "nyc_stop", "lat": 40.71, "lon": -74.00},
            ]
        },
        check_toronto_boundary=True,
        min_spacing_m=100,
        max_route_distance_m=5000,
    )
    result = constraint_check(args)

    outside_viols = [v for v in result["violations"] if v["type"] == "outside_toronto_boundary"]
    assert len(outside_viols) == 1
    assert result["feasible"] is False


def test_constraint_check_boundary_disabled_no_boundary_violations():
    """Disabling boundary check should not produce boundary violations."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "nyc_stop", "lat": 40.71, "lon": -74.00},
            ]
        },
        check_toronto_boundary=False,
        min_spacing_m=100,
        max_route_distance_m=5000,
        stop_budget=10,
    )
    result = constraint_check(args)

    outside_viols = [v for v in result["violations"] if v["type"] == "outside_toronto_boundary"]
    assert len(outside_viols) == 0


def test_constraint_check_violation_count_matches_violations_list():
    """violation_count must equal len(violations)."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "nyc1", "lat": 40.71, "lon": -74.00},
                {"stop_id": "nyc2", "lat": 40.71, "lon": -74.001},
            ]
        },
        min_spacing_m=5000,  # 2 stops definitely < 5 km apart
        check_toronto_boundary=True,
        max_route_distance_m=5000,
    )
    result = constraint_check(args)

    assert result["violation_count"] == len(result["violations"])


def test_constraint_check_feasible_false_when_violations():
    """feasible must be False when there are any violations."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "nyc", "lat": 40.71, "lon": -74.00},
            ]
        },
        check_toronto_boundary=True,
        max_route_distance_m=5000,
    )
    result = constraint_check(args)

    if result["violation_count"] > 0:
        assert result["feasible"] is False


def test_constraint_check_feasible_true_when_no_violations():
    """feasible must be True when there are zero violations."""
    args = ConstraintCheckArgs(
        layout={
            "stops": [
                {"stop_id": "ok1", "lat": 43.65, "lon": -79.38},
            ]
        },
        min_spacing_m=100,
        max_route_distance_m=5000,  # very generous
        stop_budget=5,
        check_toronto_boundary=True,
    )
    result = constraint_check(args)

    if result["violation_count"] == 0:
        assert result["feasible"] is True


def test_constraint_check_single_stop_no_spacing_violations():
    """A single stop cannot violate spacing constraints."""
    args = ConstraintCheckArgs(
        layout={"stops": [{"stop_id": "solo", "lat": 43.65, "lon": -79.38}]},
        min_spacing_m=1000,
        max_route_distance_m=5000,
        stop_budget=5,
    )
    result = constraint_check(args)

    spacing_viols = [v for v in result["violations"] if v["type"] == "stops_too_close"]
    assert len(spacing_viols) == 0


def test_constraint_check_stops_in_result_matches_input():
    """Result 'stops' list must have one entry per input stop."""
    stops = [{"stop_id": f"s{i}", "lat": 43.64 + i * 0.01, "lon": -79.38} for i in range(4)]
    args = ConstraintCheckArgs(
        layout={"stops": stops},
        min_spacing_m=50,
        max_route_distance_m=5000,
        stop_budget=10,
    )
    result = constraint_check(args)

    assert len(result["stops"]) == 4
    result_ids = {s["stop_id"] for s in result["stops"]}
    assert result_ids == {f"s{i}" for i in range(4)}


# ---------------------------------------------------------------------------
# constraint_check — input validation
# ---------------------------------------------------------------------------


def test_constraint_check_empty_stops_raises():
    with pytest.raises(ValidationError):
        ConstraintCheckArgs(layout={"stops": []})  # min_length=1


def test_constraint_check_stop_missing_stop_id():
    with pytest.raises(ValidationError):
        ConstraintCheckArgs(
            layout={"stops": [{"lat": 43.65, "lon": -79.38}]}  # missing stop_id
        )


def test_constraint_check_invalid_min_spacing():
    with pytest.raises(ValidationError):
        ConstraintCheckArgs(
            layout={"stops": [{"stop_id": "x", "lat": 43.65, "lon": -79.38}]},
            min_spacing_m=0,
        )


def test_constraint_check_invalid_budget_zero():
    with pytest.raises(ValidationError):
        ConstraintCheckArgs(
            layout={"stops": [{"stop_id": "x", "lat": 43.65, "lon": -79.38}]},
            stop_budget=0,
        )
