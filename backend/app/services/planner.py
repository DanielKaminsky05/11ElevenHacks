"""Planner service — translate a plain-English goal into RL reward weights.

Transport-agnostic and pure: no FastAPI, no I/O. The router (and later the agent
loop) call `plan_goal`. Today this is a deterministic keyword mapper so the app
runs end-to-end with no model; swap the body of `plan_goal` for a Nemotron NIM
call (parse the goal into structured weights) when the agent lands — the
`PlannerResponse` contract stays the same.
"""

from __future__ import annotations

import re

from app.schemas.planner import PlannerResponse, RewardWeights

# Each rule: (compiled keyword pattern, channel to boost, boost amount, reason).
_RULES: list[tuple[re.Pattern[str], str, float, str]] = [
    (
        re.compile(r"equity|low.?income|marginal|vulnerable|senior|newcomer|disadvantage", re.I),
        "equity",
        3.0,
        "weighting equity for vulnerable populations",
    ),
    (
        re.compile(r"coverage|gap|access|reach|underserved|desert|walk", re.I),
        "coverage",
        3.0,
        "prioritizing coverage of underserved areas",
    ),
    (
        re.compile(r"commute|travel time|fast|speed|downtown|job|employment", re.I),
        "travel_time",
        2.0,
        "protecting travel times to key destinations",
    ),
    (
        re.compile(r"without|don'?t|do not|keep|maintain|avoid|protect|budget|cost|spacing", re.I),
        "constraints",
        2.0,
        "respecting your stated constraints",
    ),
]


def _normalize(raw: dict[str, float]) -> RewardWeights:
    """Scale the four raw channel weights so they sum to 1 (rounded to 0.01)."""
    total = sum(raw.values()) or 1.0
    rounded = {k: round(v / total, 2) for k, v in raw.items()}
    return RewardWeights(
        coverage=rounded["coverage"],
        travel_time=rounded["travel_time"],
        equity=rounded["equity"],
        constraints=rounded["constraints"],
    )


def plan_goal(goal: str) -> PlannerResponse:
    """Infer reward weights + a readable reply from a plain-English goal.

    Deterministic keyword stub. Every channel starts at 1.0 (a balanced default);
    matching keywords boost the relevant channel, then weights are normalized.
    """
    raw = {"coverage": 1.0, "travel_time": 1.0, "equity": 1.0, "constraints": 1.0}
    reasons: list[str] = []

    for pattern, channel, boost, reason in _RULES:
        if pattern.search(goal):
            raw[channel] += boost
            reasons.append(reason)

    weights = _normalize(raw)
    reason_text = (
        ", ".join(reasons)
        if reasons
        else "balancing coverage, travel time, equity, and constraints"
    )

    reply = (
        f"Got it — I'll optimize stop placement by {reason_text}. "
        f"Translated into reward weights: coverage {weights.coverage}, "
        f"travel-time {weights.travel_time}, equity {weights.equity}, "
        f"constraints {weights.constraints}. "
        f"Run the agent to watch it relocate stops toward this goal."
    )

    return PlannerResponse(reply=reply, weights=weights)
