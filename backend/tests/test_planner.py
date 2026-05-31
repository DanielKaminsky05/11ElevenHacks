"""Tests for the planner service (pure) and the POST /planner endpoint."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.planner import plan_goal


def test_weights_sum_to_one():
    res = plan_goal("anything at all")
    w = res.weights
    assert abs(w.coverage + w.travel_time + w.equity + w.constraints - 1.0) < 0.02


def test_equity_goal_boosts_equity():
    res = plan_goal("prioritize equity for low-income, marginalized neighbourhoods")
    w = res.weights
    # equity should dominate the four channels for an equity-framed goal
    assert w.equity == max(w.coverage, w.travel_time, w.equity, w.constraints)


def test_coverage_goal_boosts_coverage():
    res = plan_goal("close the biggest transit coverage gaps and improve access")
    assert res.weights.coverage >= res.weights.travel_time


def test_endpoint_returns_camelcase_weights():
    with TestClient(app) as client:
        resp = client.post(
            "/planner",
            json={
                "goal": "improve access in Scarborough without raising downtown commute times",
                "history": [],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body
    # The JSON contract uses camelCase `travelTime` to match the frontend.
    assert set(body["weights"]) == {"coverage", "travelTime", "equity", "constraints"}


def test_endpoint_rejects_empty_goal():
    with TestClient(app) as client:
        resp = client.post("/planner", json={"goal": "", "history": []})
    assert resp.status_code == 422
