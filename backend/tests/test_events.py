"""Tests for the /events endpoint and the road-closure mock data."""

from datetime import date

from fastapi.testclient import TestClient

from app.data.events_mock import get_provider
from app.main import app


def test_events_endpoint_returns_list():
    with TestClient(app) as client:
        resp = client.get("/events", params={"as_of": "2026-06-01", "days_ahead": 90})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["events"])
    assert body["count"] > 0


def test_events_filter_by_category_closure():
    with TestClient(app) as client:
        resp = client.get(
            "/events",
            params={"as_of": "2026-06-01", "days_ahead": 120, "category": "closure"},
        )
    assert resp.status_code == 200
    cats = {e["category"] for e in resp.json()["events"]}
    assert cats <= {"closure"}


def test_road_closures_present_in_mock():
    ids = {e.id for e in get_provider().fetch()}
    # The six fake road closures we added.
    road_ids = {i for i in ids if i.startswith("road-")}
    assert len(road_ids) >= 6


def test_road_closures_are_supply_disruptions_with_affected_lines():
    road = [e for e in get_provider().fetch() if e.id.startswith("road-")]
    assert road, "expected road-closure events"
    for ev in road:
        assert ev.kind.value == "supply_disruption"
        assert ev.category.value == "closure"
        assert ev.impact.affected_lines, f"{ev.id} should list affected lines"


def test_default_as_of_is_today():
    with TestClient(app) as client:
        resp = client.get("/events")
    assert resp.status_code == 200
    assert resp.json()["as_of"] == date.today().isoformat()
