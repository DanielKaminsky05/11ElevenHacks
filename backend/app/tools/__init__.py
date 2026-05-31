"""The tool layer.

Tools are plain, transport-agnostic functions registered via the `@tool`
decorator in `registry.py`. The same registry feeds three consumers:
  1. the Nemotron agent loop (native tool-calling schemas),
  2. per-tool REST endpoints (direct curl/test, no model) — see routers/tools.py,
  3. the MCP server (added last).

Each tool family lives in its own module; importing them here fires their
`@tool` registrations so the registry is populated on package import.
"""

from app.tools.registry import ToolSpec, get_tool, list_tools, openai_tool_schemas, tool

# Import families for their registration side effects. Safe even when empty.
from app.tools import (  # noqa: E402,F401
    city_state,
    diagnostics,
    events,
    explanation,
    optimization,
    simulation,
)

__all__ = ["ToolSpec", "get_tool", "list_tools", "openai_tool_schemas", "tool"]
