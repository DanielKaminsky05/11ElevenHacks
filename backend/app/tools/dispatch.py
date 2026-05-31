"""Sync/async-aware tool invocation.

Tools come in two flavours and must be run differently:
  - sync `def` tools are CPU/GPU-bound and blocking → offload to a threadpool so
    they never freeze the event loop;
  - async `def` tools are I/O-bound (they await the NIM) → await them directly.

`run_tool` picks the right path so callers (the REST router, the agent loop) don't
have to care which kind a tool is.
"""

from __future__ import annotations

import inspect

from fastapi.concurrency import run_in_threadpool

from app.tools.registry import ToolSpec


async def run_tool(spec: ToolSpec, args: object) -> object:
    if inspect.iscoroutinefunction(spec.fn):
        return await spec.fn(args)
    return await run_in_threadpool(spec.fn, args)
