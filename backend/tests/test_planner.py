"""Tests for the planner service and POST /planner.

Two paths are covered:
  - the deterministic keyword mapper `plan_goal` (offline fallback), and
  - `plan_goal_model`, which delegates to the NIM-backed `parse_goal` tool.

NIM calls are always monkeypatched — no live model.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.planner import plan_goal, plan_goal_model


# --- helpers ---------------------------------------------------------------
def _nim_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _spec(**overrides) -> dict:
    base = {
        "coverage_weight": 0.4,
        "travel_weight": 0.2,
        "equity_weight": 0.3,
        "constraint_weight": 0.1,
        "region": "Scarborough",
        "budget": 6,
        "protect": None,
    }
    base.update(overrides)
    return base


def _patch_nim(content: str):
    """Patch the client the parse_goal tool uses to return a canned completion."""
    mock = MagicMock()
    mock.chat = AsyncMock(return_value=_nim_response(content))
    return patch("app.tools.optimization.get_nim_client", return_value=mock)


# --- keyword mapper (offline fallback) -------------------------------------
def test_weights_sum_to_one():
    res = plan_goal("anything at all")
    w = res.weights
    assert abs(w.coverage + w.travel_time + w.equity + w.constraints - 1.0) < 0.02


def test_equity_goal_boosts_equity():
    res = plan_goal("prioritize equity for low-income, marginalized neighbourhoods")
    w = res.weights
    assert w.equity == max(w.coverage, w.travel_time, w.equity, w.constraints)


def test_coverage_goal_boosts_coverage():
    res = plan_goal("close the biggest transit coverage gaps and improve access")
    assert res.weights.coverage >= res.weights.travel_time


# --- model-backed path -----------------------------------------------------
def test_model_path_maps_spec_to_weights():
    # An equity-dominant RewardSpec should yield an equity-dominant RewardWeights.
    with _patch_nim(json.dumps(_spec(equity_weight=0.7, coverage_weight=0.1,
                                     travel_weight=0.1, constraint_weight=0.1,
                                     region="Scarborough"))):
        res = asyncio.run(plan_goal_model("help low-income Scarborough"))
    w = res.weights
    assert w.equity == max(w.coverage, w.travel_time, w.equity, w.constraints)
    assert abs(w.coverage + w.travel_time + w.equity + w.constraints - 1.0) < 0.02
    assert "Scarborough" in res.reply  # reply is built from the spec's region


def test_model_path_falls_back_on_non_json():
    # If the model returns prose, the planner falls back to the keyword mapper.
    with _patch_nim("Sorry, I cannot help with that."):
        res = asyncio.run(plan_goal_model("close coverage gaps and improve access"))
    w = res.weights
    assert abs(w.coverage + w.travel_time + w.equity + w.constraints - 1.0) < 0.02
    assert w.coverage >= w.travel_time  # keyword fallback honored the goal


# --- endpoint contract -----------------------------------------------------
def test_endpoint_returns_camelcase_weights():
    with _patch_nim(json.dumps(_spec())):
        with TestClient(app) as client:
            resp = client.post(
                "/planner",
                json={"goal": "improve access in Scarborough", "history": []},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body
    assert set(body["weights"]) == {"coverage", "travelTime", "equity", "constraints"}


def test_endpoint_rejects_empty_goal():
    with TestClient(app) as client:
        resp = client.post("/planner", json={"goal": "", "history": []})
    assert resp.status_code == 422
