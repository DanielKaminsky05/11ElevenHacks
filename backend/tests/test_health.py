"""Smoke tests — prove the app boots (lifespan runs) and answers without a GPU."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_ok():
    # Context manager triggers lifespan (city-grid load stub).
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["grid_loaded"] is False  # stubbed until the data layer lands


# POST /chat now runs the real agent loop — see tests/test_chat.py for its coverage.
