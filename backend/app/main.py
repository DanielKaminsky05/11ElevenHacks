"""FastAPI application assembly.

Thin by design: lifespan + middleware + router includes only. No business logic
lives here — see app/routers, app/ws, app/tools.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import chat, health, tools
from app.state import AppState, load_city_grid
from app.ws import training

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown. Load the city grid once into shared state."""
    settings = get_settings()
    app.state.settings = settings
    app.state.app_state = AppState()

    logger.info("startup: loading city grid")
    load_city_grid(
        app.state.app_state,
        data_dir=settings.data_dir,
        resolution=settings.grid_resolution,
    )

    yield

    logger.info("shutdown")


app = FastAPI(title="TransitRL Backend", version="0.1.0", lifespan=lifespan)

# The browser (laptop) is a different origin than this host (the Spark), so CORS
# is required for the frontend to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(tools.router)
app.include_router(training.router)


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.api_host, port=s.api_port, reload=True)
