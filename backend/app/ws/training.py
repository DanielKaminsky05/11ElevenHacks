"""Training stream — streams RL episode metrics so the map animates as the agent learns.

STUB: accepts a connection, confirms it, and echoes until disconnect. The real
handler will consume from a queue that the background training worker fills, and
must stay lean (no compute in the socket handler itself).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/training")
async def training(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_json({"type": "connected", "message": "training stream stub"})
    try:
        while True:
            msg = await ws.receive_text()
            # TODO: replace echo with episode metrics pushed from the training worker.
            await ws.send_json({"type": "echo", "data": msg})
    except WebSocketDisconnect:
        logger.info("training stream disconnected")
