"""Schemas for the planner endpoint.

The planner turns a plain-English transit goal into (a) reward weights for the
RL agent and (b) a human-readable reply. These models are the API contract the
Next.js planner chat consumes; the JSON uses camelCase keys (via aliases) to
match the frontend's `lib/planner.ts` types exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["user", "assistant", "system"]


class ChatTurn(BaseModel):
    """One prior message in the conversation, sent back for context."""

    role: ChatRole
    content: str


class RewardWeights(BaseModel):
    """The four reward channels the RL agent optimizes (see project-idea.md).

    Each is a normalized 0–1 weight; together they sum to ~1.
    """

    model_config = ConfigDict(populate_by_name=True)

    coverage: float = Field(..., ge=0.0, le=1.0, description="Population within walking distance of a stop")
    travel_time: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        serialization_alias="travelTime",
        description="Distance from people to their nearest stop",
    )
    equity: float = Field(..., ge=0.0, le=1.0, description="Extra weight on disadvantaged areas")
    constraints: float = Field(..., ge=0.0, le=1.0, description="Spacing / proximity penalties")


class PlannerRequest(BaseModel):
    """A planner goal plus prior conversation turns for context."""

    goal: str = Field(..., min_length=1, description="The transit goal in plain English")
    history: list[ChatTurn] = Field(default_factory=list, description="Prior chat turns")


class PlannerResponse(BaseModel):
    """The planner's reply and the reward weights it inferred from the goal."""

    reply: str = Field(..., description="Human-readable plan summary")
    weights: RewardWeights = Field(..., description="Reward weights inferred from the goal")
