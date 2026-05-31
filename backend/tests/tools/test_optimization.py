"""Tests for Family D — Optimization tools.

Covers: parse_goal, optimize_layout, propose_candidates, optimization_status.

NIM calls are always monkeypatched — no live model.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.optimization import (
    OptimizationStatusArgs,
    OptimizeLayoutArgs,
    ParseGoalArgs,
    ProposeCandidatesArgs,
    RewardSpec,
    _JOBS,
    _GRID_COLS,
    _GRID_ROWS,
    _reward,
    _greedy_place,
    optimize_layout,
    optimization_status,
    parse_goal,
    propose_candidates,
)
from app.tools.registry import get_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nim_response(content: str) -> dict:
    """Build a minimal fake NIM chat-completions response."""
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}}
        ]
    }


def _valid_spec_dict(**overrides) -> dict:
    base = {
        "coverage_weight": 0.4,
        "travel_weight": 0.2,
        "equity_weight": 0.3,
        "constraint_weight": 0.1,
        "region": "Scarborough",
        "budget": 4,
        "protect": None,
    }
    base.update(overrides)
    return base


def _patch_nim(response_json: dict):
    """Context manager that patches get_nim_client to return a mock with async chat."""
    mock_client = MagicMock()
    mock_client.chat = AsyncMock(return_value=response_json)
    return patch("app.tools.optimization.get_nim_client", return_value=mock_client)


# ---------------------------------------------------------------------------
# RewardSpec validation
# ---------------------------------------------------------------------------


class TestRewardSpec:
    def test_valid_spec_constructs(self):
        spec = RewardSpec(**_valid_spec_dict())
        assert spec.region == "Scarborough"
        assert spec.budget == 4

    def test_weight_must_be_in_0_1(self):
        with pytest.raises(Exception):
            RewardSpec(coverage_weight=1.5, region="Toronto", budget=3)

    def test_negative_weight_rejected(self):
        with pytest.raises(Exception):
            RewardSpec(equity_weight=-0.1, region="Toronto", budget=3)

    def test_budget_must_be_positive(self):
        with pytest.raises(Exception):
            RewardSpec(region="Toronto", budget=0)

    def test_all_zero_weights_rejected(self):
        with pytest.raises(Exception):
            RewardSpec(
                coverage_weight=0.0,
                travel_weight=0.0,
                equity_weight=0.0,
                constraint_weight=0.0,
                region="Toronto",
                budget=3,
            )

    def test_protect_can_be_none(self):
        spec = RewardSpec(region="Toronto", budget=2, protect=None)
        assert spec.protect is None

    def test_protect_can_be_string(self):
        spec = RewardSpec(region="Toronto", budget=2, protect="downtown_commute")
        assert spec.protect == "downtown_commute"

    def test_schema_is_produced(self):
        schema = RewardSpec.model_json_schema()
        assert "properties" in schema
        assert "coverage_weight" in schema["properties"]


# ---------------------------------------------------------------------------
# Internal reward function
# ---------------------------------------------------------------------------


class TestRewardFunction:
    def test_empty_stops_gives_zero_reward(self):
        spec = RewardSpec(**_valid_spec_dict())
        assert _reward([], spec) == 0.0

    def test_single_central_stop_gives_positive_reward(self):
        spec = RewardSpec(**_valid_spec_dict())
        r = _reward([(_GRID_ROWS // 2, _GRID_COLS // 2)], spec)
        assert 0.0 < r <= 1.0

    def test_reward_never_exceeds_one(self):
        spec = RewardSpec(**_valid_spec_dict())
        stops = [(r, c) for r in range(0, _GRID_ROWS, 4) for c in range(0, _GRID_COLS, 4)]
        r = _reward(stops, spec)
        assert r <= 1.0

    def test_more_stops_does_not_decrease_coverage_reward(self):
        spec = RewardSpec(coverage_weight=1.0, travel_weight=0.0, equity_weight=0.0,
                          constraint_weight=0.0, region="Toronto", budget=10)
        stops_few = [(5, 5)]
        stops_more = [(5, 5), (5, 15), (10, 10)]
        r_few = _reward(stops_few, spec)
        r_more = _reward(stops_more, spec)
        assert r_more >= r_few

    def test_reward_is_deterministic(self):
        spec = RewardSpec(**_valid_spec_dict())
        stops = [(2, 3), (7, 14)]
        assert _reward(stops, spec) == _reward(stops, spec)


# ---------------------------------------------------------------------------
# Internal greedy placer
# ---------------------------------------------------------------------------


class TestGreedyPlace:
    def test_returns_correct_number_of_stops(self):
        spec = RewardSpec(**_valid_spec_dict(budget=3))
        result = _greedy_place(spec, seed=42)
        assert len(result) == 3

    def test_stops_within_grid_bounds(self):
        spec = RewardSpec(**_valid_spec_dict(budget=5))
        for row, col in _greedy_place(spec, seed=7):
            assert 0 <= row < _GRID_ROWS
            assert 0 <= col < _GRID_COLS

    def test_determinism_with_same_seed(self):
        spec = RewardSpec(**_valid_spec_dict(budget=4))
        assert _greedy_place(spec, seed=99) == _greedy_place(spec, seed=99)

    def test_different_seeds_may_differ(self):
        spec = RewardSpec(**_valid_spec_dict(budget=6))
        r1 = _greedy_place(spec, seed=1)
        r2 = _greedy_place(spec, seed=2)
        # Not guaranteed to differ, but with enough budget they almost always do
        # We just ensure both are valid
        for row, col in r1 + r2:
            assert 0 <= row < _GRID_ROWS

    def test_greedy_reward_non_decreasing(self):
        """Each greedy step must not lower the total reward."""
        spec = RewardSpec(**_valid_spec_dict(budget=5))
        cells_placed: list[tuple[int, int]] = []
        prev_r = _reward([], spec)
        for r, c in _greedy_place(spec, seed=42):
            cells_placed.append((r, c))
            new_r = _reward(cells_placed, spec)
            assert new_r >= prev_r - 1e-9, (
                f"Reward decreased: {prev_r} → {new_r} after placing ({r},{c})"
            )
            prev_r = new_r

    def test_budget_one_returns_single_stop(self):
        spec = RewardSpec(**_valid_spec_dict(budget=1))
        result = _greedy_place(spec, seed=0)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# parse_goal
# ---------------------------------------------------------------------------


class TestParseGoal:
    def test_schema_validity_and_registry(self):
        spec = get_tool("parse_goal")
        assert spec.name == "parse_goal"
        schema = ParseGoalArgs.model_json_schema()
        assert "text" in schema["properties"]

    def test_happy_path_returns_reward_spec(self):
        nim_payload = _valid_spec_dict(region="Scarborough", budget=8)
        with _patch_nim(_nim_response(json.dumps(nim_payload))):
            result = asyncio.run(parse_goal(ParseGoalArgs(
                text="Improve access for low-income Scarborough without raising downtown commute times."
            )))
        assert "reward_spec" in result
        spec = RewardSpec(**result["reward_spec"])
        assert spec.region == "Scarborough"
        assert spec.budget == 8
        assert 0.0 <= spec.coverage_weight <= 1.0
        assert 0.0 <= spec.equity_weight <= 1.0

    def test_prompt_contains_goal_text(self):
        """Tool must pass the goal text to the NIM, not something else."""
        nim_payload = _valid_spec_dict()
        captured_messages: list = []

        async def fake_chat(messages, tools=None):
            captured_messages.extend(messages)
            return _nim_response(json.dumps(nim_payload))

        mock_client = MagicMock()
        mock_client.chat = fake_chat
        with patch("app.tools.optimization.get_nim_client", return_value=mock_client):
            asyncio.run(parse_goal(ParseGoalArgs(text="Unique planning goal text XYZ")))

        user_msg = next(m for m in captured_messages if m["role"] == "user")
        assert "Unique planning goal text XYZ" in user_msg["content"]

    def test_malformed_json_from_nim_returns_graceful_error(self):
        with _patch_nim(_nim_response("This is not JSON at all!")):
            result = asyncio.run(parse_goal(ParseGoalArgs(text="Some planning goal here")))
        assert "error" in result
        assert "reward_spec" in result  # fallback defaults present
        spec = RewardSpec(**result["reward_spec"])
        assert spec.budget > 0

    def test_invalid_spec_from_nim_returns_graceful_error(self):
        bad = {"coverage_weight": 99.9, "region": "Toronto", "budget": -1}
        with _patch_nim(_nim_response(json.dumps(bad))):
            result = asyncio.run(parse_goal(ParseGoalArgs(text="Some planning goal here")))
        assert "error" in result
        assert "reward_spec" in result

    def test_short_text_rejected_by_validation(self):
        with pytest.raises(Exception):
            ParseGoalArgs(text="Hi")

    def test_protect_field_propagated(self):
        payload = _valid_spec_dict(protect="downtown_commute")
        with _patch_nim(_nim_response(json.dumps(payload))):
            result = asyncio.run(parse_goal(ParseGoalArgs(
                text="Protect downtown commute times while improving Scarborough coverage."
            )))
        assert result["reward_spec"]["protect"] == "downtown_commute"

    def test_offline_fake_client_returns_valid_fallback(self):
        """FakeNIMClient returns prose (not JSON); parse_goal must fall back gracefully."""
        from app.agent.nim_client import FakeNIMClient
        fake = FakeNIMClient()
        with patch("app.tools.optimization.get_nim_client", return_value=fake):
            result = asyncio.run(parse_goal(ParseGoalArgs(
                text="Improve transit in downtown core for all residents."
            )))
        # Must not crash; must return a valid RewardSpec via fallback
        assert "reward_spec" in result
        spec = RewardSpec(**result["reward_spec"])
        assert spec.budget > 0
        # Offline fallback always sets an error because the prose isn't JSON
        assert "error" in result


# ---------------------------------------------------------------------------
# optimize_layout
# ---------------------------------------------------------------------------


class TestOptimizeLayout:
    def test_schema_validity_and_registry(self):
        spec = get_tool("optimize_layout")
        assert spec.name == "optimize_layout"

    def test_happy_path_returns_expected_keys(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=42)
        result = optimize_layout(args)
        for key in ("job_id", "region", "budget", "stops", "final_reward",
                    "reward_trajectory", "elapsed_s", "method"):
            assert key in result, f"missing key {key!r}"

    def test_stop_count_matches_budget(self):
        budget = 4
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=budget), seed=0)
        result = optimize_layout(args)
        assert len(result["stops"]) == budget

    def test_stops_have_lon_lat(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=2), seed=1)
        result = optimize_layout(args)
        for stop in result["stops"]:
            assert "lon" in stop and "lat" in stop
            assert -80.0 < stop["lon"] < -79.0
            assert 43.0 < stop["lat"] < 44.0

    def test_reward_trajectory_non_decreasing(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=5), seed=42)
        result = optimize_layout(args)
        traj = result["reward_trajectory"]
        assert len(traj) >= 2
        for i in range(1, len(traj)):
            assert traj[i] >= traj[i - 1] - 1e-9, (
                f"Reward decreased at step {i}: {traj[i-1]} → {traj[i]}"
            )

    def test_final_reward_in_0_1(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=5)
        result = optimize_layout(args)
        assert 0.0 <= result["final_reward"] <= 1.0

    def test_determinism_same_seed(self):
        args1 = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=77)
        args2 = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=77)
        r1 = optimize_layout(args1)
        r2 = optimize_layout(args2)
        assert r1["stops"] == r2["stops"]
        assert r1["final_reward"] == r2["final_reward"]

    def test_job_registered_in_store(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=2), seed=3)
        result = optimize_layout(args)
        job_id = result["job_id"]
        assert job_id in _JOBS

    def test_invalid_reward_spec_returns_error(self):
        # budget=0 violates the gt=0 constraint → RewardSpec validation error
        args = OptimizeLayoutArgs(reward_spec={"region": "Toronto", "budget": 0}, seed=0)
        result = optimize_layout(args)
        assert "error" in result

    def test_cpu_method_flagged(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=2), seed=0)
        result = optimize_layout(args)
        assert result["method"] == "cpu_greedy"

    def test_budget_one(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=1), seed=0)
        result = optimize_layout(args)
        assert len(result["stops"]) == 1
        assert len(result["reward_trajectory"]) >= 2


# ---------------------------------------------------------------------------
# propose_candidates
# ---------------------------------------------------------------------------


class TestProposeCandidates:
    def test_schema_validity_and_registry(self):
        spec = get_tool("propose_candidates")
        assert spec.name == "propose_candidates"

    def test_happy_path_returns_n_candidates(self):
        n = 4
        cells = [{"row": r, "col": c} for r, c in [(2, 3), (5, 8), (10, 1), (0, 15)]]
        with _patch_nim(_nim_response(json.dumps(cells))):
            result = asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Improve Scarborough access", n=n)))
        assert len(result["candidates"]) == n

    def test_candidates_have_lon_lat_and_cell(self):
        cells = [{"row": 3, "col": 5}, {"row": 11, "col": 17}]
        with _patch_nim(_nim_response(json.dumps(cells))):
            result = asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Expand coverage downtown", n=2)))
        for cand in result["candidates"]:
            assert "row" in cand and "col" in cand
            assert "lon" in cand and "lat" in cand
            assert 0 <= cand["row"] < _GRID_ROWS
            assert 0 <= cand["col"] < _GRID_COLS

    def test_malformed_nim_response_falls_back_to_greedy(self):
        with _patch_nim(_nim_response("not json")):
            result = asyncio.run(propose_candidates(ProposeCandidatesArgs(
                goal="Improve Jane and Finch transit", n=5, seed=42
            )))
        assert len(result["candidates"]) == 5
        assert result.get("fallback") is True
        assert "parse_error" in result

    def test_out_of_bounds_cells_filtered(self):
        cells = [
            {"row": 999, "col": 999},  # out of bounds
            {"row": 2, "col": 3},       # valid
            {"row": 1000, "col": 5},    # out of bounds
        ]
        # The fallback triggers if too few valid candidates; with just 1 valid and n=1,
        # the valid cell should be kept.
        with _patch_nim(_nim_response(json.dumps(cells))):
            result = asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Transit goal text", n=1)))
        for cand in result["candidates"]:
            assert 0 <= cand["row"] < _GRID_ROWS
            assert 0 <= cand["col"] < _GRID_COLS

    def test_determinism_with_seed(self):
        with _patch_nim(_nim_response("bad json")):
            r1 = asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Some goal text here", n=3, seed=7)))
        with _patch_nim(_nim_response("bad json")):
            r2 = asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Some goal text here", n=3, seed=7)))
        assert r1["candidates"] == r2["candidates"]

    def test_n_validation(self):
        with pytest.raises(Exception):
            ProposeCandidatesArgs(goal="Valid goal text", n=0)
        with pytest.raises(Exception):
            ProposeCandidatesArgs(goal="Valid goal text", n=51)

    def test_goal_passed_to_nim(self):
        captured: list = []

        async def fake_chat(messages, tools=None):
            captured.extend(messages)
            return _nim_response(json.dumps([{"row": 5, "col": 10}]))

        mock_client = MagicMock()
        mock_client.chat = fake_chat
        with patch("app.tools.optimization.get_nim_client", return_value=mock_client):
            asyncio.run(propose_candidates(ProposeCandidatesArgs(goal="Unique goal ABCDEFG", n=1)))

        user_msg = next(m for m in captured if m["role"] == "user")
        assert "Unique goal ABCDEFG" in user_msg["content"]


# ---------------------------------------------------------------------------
# optimization_status
# ---------------------------------------------------------------------------


class TestOptimizationStatus:
    def test_schema_validity_and_registry(self):
        spec = get_tool("optimization_status")
        assert spec.name == "optimization_status"

    def test_unknown_job_id_returns_not_found(self):
        result = optimization_status(OptimizationStatusArgs(job_id="no-such-job-xyz"))
        assert result["status"] == "not_found"
        assert "error" in result
        assert result["reward_trajectory"] == []

    def test_known_job_returns_trajectory(self):
        # Run an optimization job first so it's stored
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=11)
        opt_result = optimize_layout(args)
        job_id = opt_result["job_id"]

        status = optimization_status(OptimizationStatusArgs(job_id=job_id))
        assert status["job_id"] == job_id
        assert status["status"] == "completed"
        assert isinstance(status["reward_trajectory"], list)
        assert len(status["reward_trajectory"]) >= 1

    def test_status_has_expected_keys(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=2), seed=55)
        opt_result = optimize_layout(args)
        job_id = opt_result["job_id"]

        status = optimization_status(OptimizationStatusArgs(job_id=job_id))
        for key in ("job_id", "status", "reward_trajectory", "final_reward", "region", "stops"):
            assert key in status, f"missing key {key!r}"

    def test_empty_job_id_rejected(self):
        with pytest.raises(Exception):
            OptimizationStatusArgs(job_id="")

    def test_final_reward_matches_optimize_output(self):
        args = OptimizeLayoutArgs(reward_spec=_valid_spec_dict(budget=3), seed=22)
        opt_result = optimize_layout(args)
        job_id = opt_result["job_id"]

        status = optimization_status(OptimizationStatusArgs(job_id=job_id))
        assert abs(status["final_reward"] - opt_result["final_reward"]) < 1e-9
