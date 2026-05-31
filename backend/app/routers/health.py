"""Liveness / reachability endpoint.

Used by the frontend machine to confirm it can reach the Spark over the LAN.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import app_state
from app.state import AppState

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(state: AppState = Depends(app_state)) -> dict:
    return {"status": "ok", "grid_loaded": state.grid_loaded}
