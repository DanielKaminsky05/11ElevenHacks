"""Reusable FastAPI dependencies.

Handlers depend on these rather than importing singletons directly, so tests can
override them via `app.dependency_overrides`.
"""

from __future__ import annotations

from fastapi import Request

from app.config import Settings, get_settings
from app.state import AppState


def settings_dep() -> Settings:
    return get_settings()


def app_state(request: Request) -> AppState:
    """The shared AppState populated in the lifespan."""
    return request.app.state.app_state
