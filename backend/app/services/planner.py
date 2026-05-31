"""Planner service — translate a plain-English goal into RL reward weights.

Two paths to the same `PlannerResponse` contract:

  - `plan_goal(goal)` — a deterministic keyword mapper. No model, no I/O, always
    available. It is the offline fallback and what the unit tests pin.
  - `plan_goal_model(goal)` — delegates to the registered `parse_goal` tool, which
    asks the Nemotron NIM to extract a structured `RewardSpec`, then maps that onto
    the frontend's `RewardWeights`. Falls back to `plan_goal` whenever the model is
    offline or returns something unusable.

The router calls `plan_goal_model`; the frontend contract is identical either way,
so the planner-chat UI just gets model-inferred weights when a NIM is live.
"""

from __future__ import annotations

import logging
import re

from app.schemas.planner import PlannerResponse, RewardWeights
from app.tools.optimization import ParseGoalArgs, parse_goal

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Model-backed path: delegate to the NIM-wired `parse_goal` tool
# ---------------------------------------------------------------------------


def _spec_to_weights(spec: dict) -> RewardWeights:
    """Map a RewardSpec (from `parse_goal`) onto the frontend's RewardWeights,
    normalized to sum ~1. The tool uses `*_weight` field names and need not sum
    to 1; the frontend contract uses bare channel names and does."""
    return _normalize(
        {
            "coverage": float(spec.get("coverage_weight", 0.0)),
            "travel_time": float(spec.get("travel_weight", 0.0)),
            "equity": float(spec.get("equity_weight", 0.0)),
            "constraints": float(spec.get("constraint_weight", 0.0)),
        }
    )


def _reply_from_spec(spec: dict, weights: RewardWeights) -> str:
    region = spec.get("region", "Toronto")
    budget = spec.get("budget", 5)
    protect = spec.get("protect")
    protect_note = f" while protecting {protect}" if protect else ""
    return (
        f"Got it — for {region} I'll optimize the placement of up to {budget} stops{protect_note}. "
        f"Reward weights: coverage {weights.coverage}, travel-time {weights.travel_time}, "
        f"equity {weights.equity}, constraints {weights.constraints}. "
        f"Run the agent to watch it relocate stops toward this goal."
    )


async def plan_goal_model(goal: str) -> PlannerResponse:
    """Infer weights via the NIM-backed `parse_goal` tool, falling back to the
    deterministic keyword mapper if the model is offline or returns nothing usable."""
    try:
        result = await parse_goal(ParseGoalArgs(text=goal))
    except Exception as exc:  # network down, non-OpenAI endpoint, etc.
        logger.info("parse_goal unavailable (%s); using keyword fallback", exc)
        return plan_goal(goal)

    if "error" in result or "reward_spec" not in result:
        # Model returned non-JSON / failed validation — keyword mapping beats flat defaults.
        logger.info("parse_goal returned no usable spec; using keyword fallback")
        return plan_goal(goal)

    spec = result["reward_spec"]
    weights = _spec_to_weights(spec)
    return PlannerResponse(reply=_reply_from_spec(spec, weights), weights=weights)
