"""Tool registry — the write-once mechanism behind every tool.

A tool is a function that takes a single Pydantic input model and returns a
JSON-serializable result. Registering it captures the JSON Schema (for
tool-calling) and keeps the function callable directly (for tests / REST).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

_REGISTRY: dict[str, "ToolSpec"] = {}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable


def tool(input_model: type[BaseModel]) -> Callable:
    """Decorator: register `fn` as a tool with the given Pydantic input model.

    Example:
        class Args(BaseModel):
            bbox: BBox

        @tool(Args)
        def equity_gap_report(args: Args) -> dict:
            '''Find cells with high marginalization and low transit access.'''
            ...
    """

    def deco(fn: Callable) -> Callable:
        name = fn.__name__
        if name in _REGISTRY:
            raise ValueError(f"tool {name!r} already registered")
        _REGISTRY[name] = ToolSpec(
            name=name,
            description=(fn.__doc__ or "").strip(),
            input_model=input_model,
            fn=fn,
        )
        return fn

    return deco


def list_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def get_tool(name: str) -> ToolSpec:
    return _REGISTRY[name]


def openai_tool_schemas() -> list[dict]:
    """Tool schemas in the OpenAI/NIM tool-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_model.model_json_schema(),
            },
        }
        for spec in _REGISTRY.values()
    ]
