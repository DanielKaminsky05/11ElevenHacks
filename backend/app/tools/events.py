"""TransitRL tools — Family F: Upcoming Events.

Surfaces upcoming city events (sports, festivals, closures) that perturb
transit, so the agent can mock their impact. Backed by the mock events service
(app.data.events_mock) until live feeds are wired in.

Tools:
  - find_upcoming_events: list events in a date window, filtered by kind/category/area
  - get_event: fetch a single event by id
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.data.events_mock import get_provider
from app.schemas.common import BBox
from app.schemas.events import Event, EventCategory, EventKind
from app.tools.registry import tool


def _in_bbox(ev: Event, bbox: BBox) -> bool:
    """True if the event has no coords (diffuse) or its venue falls inside bbox."""
    if ev.venue.lat is None or ev.venue.lon is None:
        return True
    return (
        bbox.west <= ev.venue.lon <= bbox.east
        and bbox.south <= ev.venue.lat <= bbox.north
    )


def _overlaps_window(ev: Event, start: datetime, end: datetime) -> bool:
    """True if the event is active at any point within [start, end]."""
    return ev.end >= start and ev.start <= end


# ===========================================================================
# Tool: find_upcoming_events
# ===========================================================================


class FindUpcomingEventsArgs(BaseModel):
    """Input for find_upcoming_events."""

    as_of: Optional[date] = Field(
        None,
        description="Window start date (inclusive). None = today.",
    )
    days_ahead: int = Field(
        60,
        ge=1,
        le=365,
        description="Length of the look-ahead window in days from as_of.",
    )
    categories: Optional[list[EventCategory]] = Field(
        None,
        description="Restrict to these categories (sports, festival, closure, ...). None = all.",
    )
    kinds: Optional[list[EventKind]] = Field(
        None,
        description="Restrict to demand_surge and/or supply_disruption. None = both.",
    )
    bbox: Optional[BBox] = Field(
        None,
        description="Restrict to events whose venue falls in this box. None = whole city.",
    )
    limit: int = Field(
        50,
        ge=1,
        le=500,
        description="Maximum number of events to return.",
    )

    @model_validator(mode="after")
    def _check_bbox(self) -> "FindUpcomingEventsArgs":
        b = self.bbox
        if b is not None:
            if b.east <= b.west:
                raise ValueError("bbox.east must be greater than bbox.west")
            if b.north <= b.south:
                raise ValueError("bbox.north must be greater than bbox.south")
        return self


@tool(FindUpcomingEventsArgs)
def find_upcoming_events(args: FindUpcomingEventsArgs) -> dict:
    """Find upcoming Toronto events (matches, festivals, closures) that affect transit."""
    start_date = args.as_of or date.today()
    # Treat the window in Eastern time so all-day comparisons line up with the data.
    et = timezone(timedelta(hours=-4))
    window_start = datetime.combine(start_date, datetime.min.time(), tzinfo=et)
    window_end = window_start + timedelta(days=args.days_ahead)

    cats = set(args.categories) if args.categories else None
    kinds = set(args.kinds) if args.kinds else None

    matched: list[Event] = []
    for ev in get_provider().fetch():
        if not _overlaps_window(ev, window_start, window_end):
            continue
        if cats is not None and ev.category not in cats:
            continue
        if kinds is not None and ev.kind not in kinds:
            continue
        if args.bbox is not None and not _in_bbox(ev, args.bbox):
            continue
        matched.append(ev)

    matched.sort(key=lambda e: e.start)
    matched = matched[: args.limit]

    return {
        "as_of": start_date.isoformat(),
        "window_days": args.days_ahead,
        "count": len(matched),
        "events": [e.model_dump(mode="json") for e in matched],
    }


# ===========================================================================
# Tool: get_event
# ===========================================================================


class GetEventArgs(BaseModel):
    """Input for get_event."""

    id: str = Field(..., min_length=1, description="Event id (e.g. 'wc-2026-06-12').")


@tool(GetEventArgs)
def get_event(args: GetEventArgs) -> dict:
    """Fetch a single upcoming event by its id."""
    for ev in get_provider().fetch():
        if ev.id == args.id:
            return {"event": ev.model_dump(mode="json")}
    known = [e.id for e in get_provider().fetch()]
    return {"error": f"no event with id {args.id!r}", "event": None, "known_ids": known}
