"""Events endpoint — upcoming city activity that perturbs transit.

  GET /events  → { as_of, window_days, count, events: [...] }

A thin adapter over the find_upcoming_events tool so the frontend news feed can
fetch with a plain GET (the generic POST /tools/{name} path also works, but a
dedicated GET is friendlier for the UI and keeps the contract obvious). The
handler body is pure synchronous compute, so it's `def` (threadpool) per
docs/best-practices/fastapi.md.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.events import EventCategory, EventKind
from app.tools.events import FindUpcomingEventsArgs, find_upcoming_events

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(
    as_of: Optional[date] = Query(None, description="Window start (inclusive). None = today."),
    days_ahead: int = Query(120, ge=1, le=365, description="Look-ahead window in days."),
    category: Optional[list[EventCategory]] = Query(None, description="Filter by category."),
    kind: Optional[list[EventKind]] = Query(None, description="Filter by kind."),
    limit: int = Query(100, ge=1, le=500, description="Max events to return."),
) -> dict:
    args = FindUpcomingEventsArgs(
        as_of=as_of,
        days_ahead=days_ahead,
        categories=category,
        kinds=kind,
        limit=limit,
    )
    return find_upcoming_events(args)
