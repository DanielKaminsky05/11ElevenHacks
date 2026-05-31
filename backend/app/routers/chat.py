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

SYSTEM_PROMPT = (
    "You are TransitRL, a transportation-planning copilot for Toronto. A city "
    "planner asks questions in plain English. Use the provided tools to diagnose "
    "transit gaps, simulate changes, optimize stop placement, and explain results "
    "over Toronto open data. Call tools to gather evidence before answering, then "
    "give a concise, numbers-grounded answer. Do not invent data the tools did not "
    "return."
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
