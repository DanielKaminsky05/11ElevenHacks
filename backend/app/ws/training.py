"""Training stream — streams optimizer per-step states so the map animates as the
network is built, and re-solves whenever the planner sends new reward weights.

The client sends a JSON message holding a `reward_spec` (as produced by
parse_goal), optionally with `seed`. The server runs the greedy + local-search
optimizer off the event loop and streams one frame per placement/swap step:

    {"type": "connected"}
    {"type": "step", "index": i, "stops": [{lon,lat}...], "R": float,
     "channel_scores": {...}}
    {"type": "done", "job_id": ..., "final_reward": ..., "stopped_reason": ...,
     "stops": [...]}

The socket handler stays lean — the actual search runs in a threadpool.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.tools.optimization import OptimizeLayoutArgs, optimize_layout

logger = logging.getLogger(__name__)

router = APIRouter()

# Pacing between streamed frames so the frontend animates the build (seconds).
_FRAME_DELAY_S = 0.05


@router.websocket("/ws/training")
async def training(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_json({"type": "connected", "message": "optimizer stream ready"})
    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                await ws.send_json({"type": "error", "error": f"invalid JSON: {exc}"})
                continue

            reward_spec = payload.get("reward_spec", payload)
            seed = int(payload.get("seed", 42))

            try:
                args = OptimizeLayoutArgs(reward_spec=reward_spec, seed=seed)
            except Exception as exc:  # pydantic validation
                await ws.send_json({"type": "error", "error": str(exc)})
                continue

            # Heavy CPU work off the event loop.
            result = await run_in_threadpool(optimize_layout, args)
            if "error" in result:
                await ws.send_json({"type": "error", "error": result["error"]})
                continue

            for i, step in enumerate(result["steps"]):
                await ws.send_json(
                    {
                        "type": "step",
                        "index": i,
                        "stops": step["stops"],
                        "R": step["R"],
                        "channel_scores": step["channel_scores"],
                    }
                )
                await asyncio.sleep(_FRAME_DELAY_S)

            await ws.send_json(
                {
                    "type": "done",
                    "job_id": result["job_id"],
                    "final_reward": result["final_reward"],
                    "channel_scores": result["channel_scores"],
                    "stopped_reason": result["stopped_reason"],
                    "stops": result["stops"],
                }
            )
    except WebSocketDisconnect:
        logger.info("training stream disconnected")
