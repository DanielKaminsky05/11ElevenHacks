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
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.agent.nim_client import get_nim_client
from app.tools import get_tool
from app.tools.dispatch import run_tool
from app.tools.registry import openai_tool_schemas

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# A tool call can spawn another; cap the loop so a misbehaving model can't spin
# forever. Each iteration is one model turn (which may request several tools).
MAX_ITERATIONS = 8

# Keep only the last N prior turns in context. Plenty for resolving "their", "those
# areas", "compare them" against the recent conversation without bloating the prompt
# (and the budget) with the entire session on every request.
MAX_HISTORY_TURNS = 10

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
    "- Adding/placing N stops in an area WITHOUT exact locations ('add 3 stops in "
    "Malvern', 'where should stops go') -> call optimize_layout right away with that "
    "region and budget=N. Naming an area and a count is ENOUGH: the weights default to a "
    "balanced mix, so do NOT ask for a 'priority goal', weights, or 'budget constraints' "
    "— set non-default weights only if the user stated a priority (e.g. 'for low-income'). "
    "Use simulate_change ONLY when the user gives specific stop locations or operations to "
    "evaluate.\n"
    "- Finding gaps/deserts -> the diagnostics tools (equity_gap_report, "
    "compute_accessibility).\n"
    "- Greetings or capability questions ('hi', 'what can you do') -> answer directly, "
    "call no tool.\n\n"
    "GROUNDING (strict — the rule that matters most):\n"
    "- Never state a number you did not get from a tool result this turn. Every figure "
    "in your answer must come from a tool you actually called.\n"
    "- Never invent coordinates, stop locations, or ids — those are data too. If calling a "
    "tool would require you to make up a location (e.g. simulate_change needs exact "
    "lat/lon you weren't given), DON'T — use optimize_layout, which derives real locations "
    "from the data, instead.\n"
    "- If you do not have the data, call the tool. Do not answer from memory or estimate.\n"
    "- Resolve the area with profile_area/get_city_grid before any area-specific claim.\n\n"
    "DON'T STALL — bias to action:\n"
    "- If a request is actionable, act with a sensible default and state it; don't just "
    "describe what you would need. Ask at most ONE brief question, and never re-ask "
    "something already asked this conversation — act instead.\n"
    "- Don't second-guess Toronto place names. Pass the name the planner gave straight to "
    "the tool — it fuzzy-matches all 158 neighbourhoods and errors only if there's truly no "
    "match. Treat an unfamiliar name as real and call the tool; clarify a name ONLY after a "
    "tool reports no match.\n\n"
    "Once you have the evidence, give a concise answer."
)


class ChatTurn(BaseModel):
    """One prior message in the conversation, replayed so the agent has memory."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior conversation turns (oldest first), so follow-ups like "
        "'their density' resolve against earlier answers. Tool steps are not replayed.",
    )


class ChatStep(BaseModel):
    """One executed tool call in the agent's trace."""

    tool: str
    arguments: dict
    result: Any


class ChatResponse(BaseModel):
    reply: str
    steps: list[ChatStep] = []


# Nemotron sometimes emits a tool call inline as text — e.g.
# `<TOOLCALL>[{"name": ..., "arguments": {...}}]</TOOLCALL>` — instead of via the
# structured `tool_calls` field. Without salvage the loop runs no tool and the raw
# markup leaks to the user. Matches <TOOLCALL>/<tool_call>/<toolcall> case-insensitively.
_TOOLCALL_RE = re.compile(
    r"<\s*tool_?call\s*>(.*?)<\s*/\s*tool_?call\s*>", re.IGNORECASE | re.DOTALL
)


def _extract_textual_tool_calls(content: str) -> list[dict] | None:
    """Salvage inline-text tool calls into OpenAI-shaped tool_calls, or None.

    Tolerates either a JSON object or a JSON array inside the tags, and serialises
    each call's arguments to the JSON string the rest of the loop expects.
    """
    if not content:
        return None
    calls: list[dict] = []
    for block in _TOOLCALL_RE.findall(content):
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict) or "name" not in item:
                continue
            args = item.get("arguments", {})
            if not isinstance(args, str):
                args = json.dumps(args)
            calls.append(
                {
                    "id": f"call_{len(calls)}",
                    "type": "function",
                    "function": {"name": item["name"], "arguments": args},
                }
            )
    return calls or None


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


async def _run_chat(req: ChatRequest) -> AsyncIterator[dict]:
    """Drive the tool-calling loop, yielding one event per stage so callers can
    react as the pipeline runs (rather than only at the end):

    - ``{"type": "tool", "tool", "arguments"}`` — emitted *before* a tool runs, so
      a UI can show a live "calling <tool>" indicator while it (and the next model
      turn) executes.
    - ``{"type": "done", "reply", "steps"}`` — the final answer plus the full
      step trace (each step's tool, arguments, result).

    Both ``/chat`` (collected into one response) and ``/chat/stream`` (Server-Sent
    Events) consume this, so the loop logic lives in exactly one place.
    """
    client = get_nim_client()
    schemas = openai_tool_schemas()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Replay recent turns so the agent can resolve references to earlier answers
    # ("their density", "compare those") instead of treating each message as fresh.
    for turn in req.history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.message})
    steps: list[ChatStep] = []

    for _ in range(MAX_ITERATIONS):
        resp = await client.chat(messages, tools=schemas)
        msg = resp["choices"][0]["message"]

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # Recover any tool call the model emitted as text rather than structure.
            salvaged = _extract_textual_tool_calls(msg.get("content") or "")
            if salvaged:
                msg = {**msg, "content": None, "tool_calls": salvaged}
                tool_calls = salvaged

        messages.append(msg)

        if not tool_calls:
            yield {
                "type": "done",
                "reply": msg.get("content") or "",
                "steps": [s.model_dump() for s in steps],
            }
            return

        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                raw_args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                raw_args = {}
            # Announce the call before running it so the UI shows it live.
            yield {"type": "tool", "tool": name, "arguments": raw_args}
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
    yield {
        "type": "done",
        "reply": "(stopped: reached the tool-call limit without a final answer)",
        "steps": [s.model_dump() for s in steps],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Run the agent loop and return the final answer + full step trace at once."""
    reply = ""
    steps: list[ChatStep] = []
    async for event in _run_chat(req):
        if event["type"] == "done":
            reply = event["reply"]
            steps = [ChatStep(**s) for s in event["steps"]]
    return ChatResponse(reply=reply, steps=steps)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Same loop as ``/chat``, streamed as Server-Sent Events: a ``tool`` event
    fires the moment the model calls each tool (so the UI can show it live), then
    a final ``done`` event carries the reply + full step trace."""

    async def event_stream() -> AsyncIterator[str]:
        async for event in _run_chat(req):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # Defeat proxy/Next buffering so events reach the browser as they happen.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
