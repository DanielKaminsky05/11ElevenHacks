"""Chat endpoint — the planning copilot's entry point.

Drives the Nemotron tool-calling loop against the tool registry: the model is
handed every tool's schema, and each tool call it emits is validated and run
locally (`app/tools`), with the result fed back until the model returns a final
answer. The whole loop runs offline against a `ScriptedFakeNIMClient` (no model)
so it is unit-testable; on the Spark `get_nim_client()` returns the real NIM.

The response carries the full step trace (tool, arguments, result) — not just the
prose — so the frontend map can react to each tool's output as the pipeline runs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError

from app.agent.nim_client import get_nim_client
from app.tools import get_tool
from app.tools.dispatch import run_tool
from app.tools.registry import openai_tool_schemas

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# A tool call can spawn another; cap the loop so a misbehaving model can't spin
# forever. Each iteration is one model turn (which may request several tools).
MAX_ITERATIONS = 8

# Nemotron's thinking mode otherwise dumps its full reasoning trace into the reply
# `content` (no <think> tags, so it can't be cleanly stripped). `/no_think` yields a
# clean user-facing answer and still emits tool_calls correctly — verified on-box.
SYSTEM_PROMPT = (
    "/no_think\n"
    "You are TransitRL, a transportation-planning copilot for Toronto. A city planner "
    "asks questions in plain English; you answer using tools over Toronto open data.\n\n"
    "ROUTING (which tool for which intent):\n"
    "- Facts about an area (population, income, low-income %, stop count) — 'what is', "
    "'how many', 'tell me about <neighbourhood>' — call profile_area (or get_city_grid "
    "for the gridded/map view).\n"
    "- Adding N stops WITHOUT exact locations ('add 3 stops in Malvern', 'where should "
    "stops go') -> optimize_layout (region + budget=N); it finds where.\n"
    "- Changing a SPECIFIC existing stop ('remove/move the King & Bathurst stop') -> first "
    "call list_transit for that area to get the real stop_id, THEN simulate_change with "
    "that id. simulate_change needs real stop_ids/coords, never made-up ones.\n"
    "- Finding gaps/deserts -> the diagnostics tools (equity_gap_report, "
    "compute_accessibility).\n"
    "- Greetings or capability questions ('hi', 'what can you do') -> answer directly, "
    "call no tool.\n\n"
    "GROUNDING (strict — the rule that matters most):\n"
    "- Never state a number you did not get from a tool result this turn. Every figure "
    "in your answer must come from a tool you actually called.\n"
    "- Never fabricate a coordinate, stop_id, or location. To ADD a stop at an unspecified "
    "place, use optimize_layout (it derives real locations). To act on an EXISTING stop, "
    "look it up with list_transit first — don't guess its id.\n"
    "- If you do not have the data, call the tool. Do not answer from memory or estimate.\n"
    "- Resolve the area with profile_area/get_city_grid before any area-specific claim.\n\n"
    "DON'T STALL: if a request is actionable but missing a detail, pick a sensible default "
    "and state it, or ask ONE brief question — never just describe what you would need.\n\n"
    "Once you have the evidence, give a concise answer."
)


class ChatRequest(BaseModel):
    message: str


class ChatStep(BaseModel):
    """One executed tool call in the agent's trace."""

    tool: str
    arguments: dict
    result: Any


class ChatResponse(BaseModel):
    reply: str
    steps: list[ChatStep] = []


def _to_json(value: Any) -> str:
    """Serialize a tool result for feeding back to the model. Tools return
    JSON-serializable values; `default=str` is a belt-and-suspenders fallback."""
    return json.dumps(value, default=str)


async def _execute_tool(name: str, raw_args: dict) -> Any:
    """Validate and run one tool. Errors are returned (not raised) so the model
    sees them as a tool result and can recover, rather than 500ing the request."""
    try:
        spec = get_tool(name)
    except KeyError:
        return {"error": f"unknown tool: {name}"}
    try:
        args = spec.input_model.model_validate(raw_args)
    except ValidationError as exc:
        return {"error": "invalid arguments", "detail": exc.errors(include_url=False)}
    return await run_tool(spec, args)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    client = get_nim_client()
    schemas = openai_tool_schemas()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": req.message},
    ]
    steps: list[ChatStep] = []

    for _ in range(MAX_ITERATIONS):
        resp = await client.chat(messages, tools=schemas)
        msg = resp["choices"][0]["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return ChatResponse(reply=msg.get("content") or "", steps=steps)

        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                raw_args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                raw_args = {}
            result = await _execute_tool(name, raw_args)
            steps.append(ChatStep(tool=name, arguments=raw_args, result=result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": name,
                    "content": _to_json(result),
                }
            )

    logger.warning("chat loop hit MAX_ITERATIONS=%d without a final answer", MAX_ITERATIONS)
    return ChatResponse(
        reply="(stopped: reached the tool-call limit without a final answer)",
        steps=steps,
    )
