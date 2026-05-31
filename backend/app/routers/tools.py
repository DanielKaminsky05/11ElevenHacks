"""Per-tool REST access — call any registered tool directly, no model involved.

  GET  /tools                 → list registered tools + their JSON schemas
  POST /tools/{name}          → validate payload against the tool's input model and run it

This is how you curl/Postman a tool in isolation for testing and the demo. The
tool body is run in a threadpool so CPU/GPU-bound compute never blocks the event
loop (see docs/best-practices/fastapi.md).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.tools import get_tool, list_tools
from app.tools.dispatch import run_tool

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_registered_tools() -> list[dict]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "schema": spec.input_model.model_json_schema(),
        }
        for spec in list_tools()
    ]


@router.post("/{name}")
async def call_tool(name: str, payload: dict) -> object:
    try:
        spec = get_tool(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
    try:
        args = spec.input_model.model_validate(payload)
    except ValidationError as exc:
        # Manually-raised ValidationError isn't auto-converted by FastAPI; do it here.
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False))
    return await run_tool(spec, args)
