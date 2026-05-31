"""TransitRL tools — Family D: Optimization.

Tools that let the machine search: parse_goal, optimize_layout,
propose_candidates, optimization_status. Register each with `@tool` from
app.tools.registry.

NOTE: the heavy RL core (optimize_layout) needs the GPU/SB3 stack on the Spark.
A deterministic CPU greedy/hill-climbing fallback is implemented here so tests
and demos run on a laptop. See # TODO(spark) comments.

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agent.nim_client import get_nim_client
from app.tools.registry import tool


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
# Internal helpers
# ---------------------------------------------------------------------------

_TORONTO_GRID_BOUNDS = {
    "lon_min": -79.6393,
    "lon_max": -79.1167,
    "lat_min": 43.5810,
    "lat_max": 43.8555,
}
_GRID_COLS = 20
_GRID_ROWS = 15


def _grid_cells() -> list[tuple[int, int]]:
    """Return all (row, col) indices of the coarse evaluation grid."""
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


def _reward(stops: list[tuple[int, int]], spec: RewardSpec) -> float:
    """Deterministic CPU reward approximation for a stop layout.

    Coverage   — fraction of grid cells within 2 grid-units of a stop.
    Travel     — inverse mean distance from each cell to its nearest stop.
    Equity     — fraction of high-equity-need cells covered (approximated by
                  cells in the lower-income quadrant of the grid, i.e. rows > half).
    Constraint — penalty for stops placed too close together (<= 1 grid unit apart).

    All terms normalised to [0, 1].
    """
    if not stops:
        return 0.0

    cells = _grid_cells()
    covered = 0
    equity_covered = 0
    equity_cells = [c for c in cells if c[0] >= _GRID_ROWS // 2]  # southern half proxy
    total_dist = 0.0

    for cell in cells:
        dists = [math.hypot(cell[0] - s[0], cell[1] - s[1]) for s in stops]
        min_dist = min(dists)
        covered += 1 if min_dist <= 2.0 else 0
        total_dist += min_dist

    for cell in equity_cells:
        dists = [math.hypot(cell[0] - s[0], cell[1] - s[1]) for s in stops]
        equity_covered += 1 if min(dists) <= 2.0 else 0

    n = len(cells)
    coverage_score = covered / n
    # travel: max possible mean dist is roughly sqrt(R²+C²)/2; normalise to [0,1]
    max_mean = math.hypot(_GRID_ROWS, _GRID_COLS) / 2
    travel_score = 1.0 - min(total_dist / n / max_mean, 1.0)
    equity_score = equity_covered / max(len(equity_cells), 1)

    # Constraint penalty: fraction of stop-pairs that are too close
    n_stops = len(stops)
    n_pairs = n_stops * (n_stops - 1) / 2 if n_stops > 1 else 1
    too_close = sum(
        1
        for i in range(n_stops)
        for j in range(i + 1, n_stops)
        if math.hypot(stops[i][0] - stops[j][0], stops[i][1] - stops[j][1]) <= 1.0
    )
    constraint_score = 1.0 - (too_close / n_pairs if n_pairs > 0 else 0.0)

    total_w = (
        spec.coverage_weight
        + spec.travel_weight
        + spec.equity_weight
        + spec.constraint_weight
    )
    if total_w == 0:
        return 0.0
    return (
        spec.coverage_weight * coverage_score
        + spec.travel_weight * travel_score
        + spec.equity_weight * equity_score
        + spec.constraint_weight * constraint_score
    ) / total_w


def _greedy_place(spec: RewardSpec, seed: int = 42) -> list[tuple[int, int]]:
    """Greedy stop placement: iteratively add the cell that maximally increases
    the weighted reward.

    # TODO(spark): replace with SB3 PPO/DQN over a Gymnasium env; warm-start
    #              candidates with cuOpt combinatorial placement.
    """
    rng = random.Random(seed)
    cells = _grid_cells()
    rng.shuffle(cells)  # break ties randomly but deterministically

    placed: list[tuple[int, int]] = []
    for _ in range(spec.budget):
        best_cell = None
        best_r = _reward(placed, spec)
        for cell in cells:
            if cell in placed:
                continue
            candidate = placed + [cell]
            r = _reward(candidate, spec)
            if r > best_r:
                best_r = r
                best_cell = cell
        if best_cell is None:
            # No improvement possible; pick a random unplaced cell
            remaining = [c for c in cells if c not in placed]
            if not remaining:
                break
            best_cell = remaining[0]
        placed.append(best_cell)

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
    """Search for a stop layout that maximises the given reward spec; returns stop locations and metric trajectory.

    CPU fallback: deterministic greedy placement. GPU path uses SB3 PPO/DQN on the Spark.
    """
    # TODO(spark): replace CPU greedy with SB3 PPO/DQN over a Gymnasium city-grid env;
    #              warm-start with cuOpt combinatorial placement; stream episodes via WebSocket.

    try:
        spec = RewardSpec(**args.reward_spec)
    except Exception as exc:
        return {"error": f"invalid reward_spec: {exc}"}

    job_id = str(uuid.uuid4())
    start = time.time()

    # Greedy placement with trajectory recording
    rng = random.Random(args.seed)
    cells = _grid_cells()
    rng.shuffle(cells)

    placed: list[tuple[int, int]] = []
    trajectory: list[float] = [_reward([], spec)]

    for step in range(min(args.max_iterations, spec.budget)):
        best_cell = None
        best_r = trajectory[-1]
        for cell in cells:
            if cell in placed:
                continue
            candidate = placed + [cell]
            r = _reward(candidate, spec)
            if r > best_r:
                best_r = r
                best_cell = cell
        if best_cell is None:
            remaining = [c for c in cells if c not in placed]
            if not remaining:
                break
            best_cell = remaining[0]
        placed.append(best_cell)
        trajectory.append(_reward(placed, spec))
        if len(placed) >= spec.budget:
            break

    final_reward = trajectory[-1]
    elapsed = time.time() - start

    # Convert to lon/lat for the output
    stop_lonlats = [_cell_to_lonlat(r, c) for r, c in placed]

    result = {
        "job_id": job_id,
        "region": spec.region,
        "budget": spec.budget,
        "stops": [{"lon": float(lon), "lat": float(lat)} for lon, lat in stop_lonlats],
        "stop_cells": [{"row": r, "col": c} for r, c in placed],
        "final_reward": float(final_reward),
        "reward_trajectory": [float(v) for v in trajectory],
        "elapsed_s": float(round(elapsed, 3)),
        "method": "cpu_greedy",  # TODO(spark): "sb3_ppo" on Spark
    }

    # Store in job store for optimization_status queries
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "reward_trajectory": result["reward_trajectory"],
        "final_reward": final_reward,
        "region": spec.region,
        "stops": result["stops"],
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
        "region": job.get("region"),
        "stops": job.get("stops", []),
        "elapsed_s": job.get("elapsed_s"),
    }
