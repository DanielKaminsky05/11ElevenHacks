"""Planner endpoint — turns a plain-English goal into RL reward weights.

  POST /planner  → { reply, weights }

Thin adapter over `app.services.planner`. The handler awaits `plan_goal_model`,
which asks the Nemotron NIM (via the `parse_goal` tool) to extract structured
weights and falls back to a deterministic keyword mapper when the model is
offline — so the endpoint always answers, with or without a live model.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.planner import PlannerRequest, PlannerResponse
from app.services.planner import plan_goal_model

router = APIRouter(tags=["agent"])


@router.post("/planner", response_model=PlannerResponse)
async def planner(req: PlannerRequest) -> PlannerResponse:
    return await plan_goal_model(req.goal)
