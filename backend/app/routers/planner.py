"""Planner endpoint — turns a plain-English goal into RL reward weights.

  POST /planner  → { reply, weights }

Thin adapter over `app.services.planner`. The handler body is pure synchronous
compute (keyword mapping), so it's declared `def` and FastAPI runs it in a
threadpool — keeping the event loop free (see docs/best-practices/fastapi.md).
When the agent loop replaces the stub with a NIM call, switch this to `async def`
and `await` the model.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.planner import PlannerRequest, PlannerResponse
from app.services.planner import plan_goal

router = APIRouter(tags=["agent"])


@router.post("/planner", response_model=PlannerResponse)
def planner(req: PlannerRequest) -> PlannerResponse:
    return plan_goal(req.goal)
