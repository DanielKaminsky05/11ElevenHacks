"""Chat endpoint — entry point for the planning copilot.

STUB: returns a placeholder so the frontend can wire against the contract now.
The real implementation runs the Nemotron tool-calling loop (app/agent) once the
tools land.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["agent"])


class ChatRequest(BaseModel):
    message: str


class ToolCall(BaseModel):
    name: str
    arguments: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCall] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # TODO: drive the Nemotron tool-calling loop against the tool registry.
    return ChatResponse(
        reply=f"(stub) received: {req.message!r}. Agent loop not implemented yet.",
        tool_calls=[],
    )
