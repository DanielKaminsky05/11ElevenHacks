"""Tests for the generic tool-dispatch router (POST /tools/{name}, GET /tools)."""

from fastapi.testclient import TestClient

from app.main import app
from app.tools import list_tools


def test_list_tools_returns_all_registered():
    with TestClient(app) as client:
        resp = client.get("/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == len(list_tools())
    # each entry exposes a name, description, and JSON schema
    for entry in body:
        assert {"name", "description", "schema"} <= entry.keys()


def test_unknown_tool_is_404():
    with TestClient(app) as client:
        resp = client.post("/tools/does_not_exist", json={})
    assert resp.status_code == 404


def test_invalid_payload_is_422():
    # threshold_m must be > 0; manually-raised ValidationError must map to 422, not 500
    with TestClient(app) as client:
        resp = client.post("/tools/compute_accessibility", json={"threshold_m": -5})
    assert resp.status_code == 422


def test_valid_call_dispatches_and_returns_200():
    with TestClient(app) as client:
        resp = client.post("/tools/reliability_report", json={"mode": "bus", "top_n": 3})
    assert resp.status_code == 200
