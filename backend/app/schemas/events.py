"""Schemas for upcoming city events that perturb transit.

An *event* is anything with a place and a time window that shocks the grid —
a stadium match (demand surge) or a line closure (supply disruption). The
`TransitImpact` block carries the *transparent assumptions* a shock model
consumes; they are deliberately coarse and human-readable, never hidden
predictions — a downstream shock model turns them into grid deltas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    sports = "sports"
    festival = "festival"
    concert = "concert"
    construction = "construction"
    closure = "closure"
    weather = "weather"


class EventKind(str, Enum):
    """Which side of the system the event shocks."""

    demand_surge = "demand_surge"          # more riders at a place/time
    supply_disruption = "supply_disruption"  # less network capacity


class Magnitude(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    severe = "severe"


class Venue(BaseModel):
    """Where the event is centred. Coords are WGS84; absent for diffuse events."""

    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class TransitImpact(BaseModel):
    """Coarse, transparent shock parameters — the inputs to a shock model.

    These are assumptions, shown to the user, not forecasts. A downstream
    `model_event_shock` tool turns them into grid deltas.
    """

    magnitude: Magnitude = Magnitude.medium
    # demand-surge params
    expected_attendance: Optional[int] = Field(
        None, description="Approximate peak crowd, for demand surges."
    )
    radius_km: Optional[float] = Field(
        None, description="How far the surge spreads from the venue."
    )
    # supply-disruption params
    affected_lines: list[str] = Field(default_factory=list)
    affected_stations: list[str] = Field(default_factory=list)
    shuttle_replacement: Optional[bool] = Field(
        None, description="Whether shuttle buses replace the closed segment."
    )


class Event(BaseModel):
    """A time-bounded event with an inferred transit impact."""

    id: str
    title: str
    category: EventCategory
    kind: EventKind
    venue: Venue
    start: datetime
    end: datetime
    impact: TransitImpact = Field(default_factory=TransitImpact)
    description: str = ""
    source: str = Field("mock", description="Provenance — 'mock' until real feeds wired in.")
